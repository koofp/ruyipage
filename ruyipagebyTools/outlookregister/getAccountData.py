# -*- coding: utf-8 -*-
"""Outlook 注册账号数据保存模块。

提供给 FirefoxOptions.py 注册成功后调用：
    from getAccountData import save_account_data
    result = save_account_data(page, email, password)

功能：
1. 从 ruyiPage page 导出 Microsoft 相关域 Cookie
2. 通过 Microsoft OAuth 提取 Graph refresh token
3. 按 reg-factory 兼容格式写入 _outlook_pool/ JSON + emails.txt
"""

import json
import os
import time
import types
import urllib.parse
from datetime import datetime, timezone
import requests
from extract_graph_tokens import get_graph_token, reg_factory_module


# ---------------------------------------------------------------------------
# localhost redirect 安全 Session（方案5）
# ---------------------------------------------------------------------------
class SafeRedirectSession(requests.Session):
    """覆写 get_redirect_target：当重定向目标是 localhost callback（含
    code=/error=）时返回 None，让 requests 不自动 follow——把原始 302
    response 返回给调用方（reg-factory 的 128-150 手动 loop 据此提 code）。

    背景：reg-factory 的 credentials POST（:111）等用 allow_redirects=True，
    微软 redirect 到 http://localhost/?code=... 时 requests 自动 follow，经
    Kookeey 代理发 localhost 请求会 ProxyError，code 明明在 URL 却拿不到。
    本类只在 localhost callback 时不 follow，其他 redirect 正常放行。
    """

    def get_redirect_target(self, resp):
        target = super().get_redirect_target(resp)
        if target:
            host = (urllib.parse.urlparse(target).hostname or "").lower()
            if host in ("localhost", "127.0.0.1") and ("code=" in target or "error=" in target):
                return None
        return target


def _patched_requests_module():
    """构造一个 fake `requests` 模块：Session=SafeRedirectSession，其余属性
    透传真 requests（reg-factory 仅用 requests.Session，但透传保证向前兼容）。
    用于临时注入 reg-factory 模块的 globals，使其 `requests.Session()` 实际
    拿到 SafeRedirectSession。"""
    fake = types.ModuleType("requests")
    for name in dir(requests):
        if name not in ("Session",):
            setattr(fake, name, getattr(requests, name))
    fake.Session = SafeRedirectSession
    return fake

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
COOKIE_DOMAINS = (
    "outlook.com",
    "live.com",
    "login.live.com",
    "microsoftonline.com",
    "microsoft.com",
    "office.com",
    "office365.com",
    "msn.com",
    "bing.com",
    "mail.live.com",
)



# ---------------------------------------------------------------------------
# Cookie 导出
# ---------------------------------------------------------------------------
def _export_cookies(page):
    """从 ruyiPage page 导出 Microsoft 相关域 cookie，返回 dict 列表。"""
    try:
        page.wait(2)
        raw = page.get_cookies(all_info=True)
    except Exception as exc:
        print("[getAccountData] cookie 导出失败: {}: {}".format(type(exc).__name__, exc))
        return []

    cookies = []
    for c in raw:
        try:
            if isinstance(c, dict):
                info = {
                    "name": c.get("name", ""),
                    "value": c.get("value", ""),
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                    "httpOnly": c.get("httpOnly", c.get("http_only", False)),
                    "secure": c.get("secure", False),
                    "sameSite": c.get("sameSite", c.get("same_site", "")),
                }
            else:
                info = {
                    "name": getattr(c, "name", ""),
                    "value": getattr(c, "value", ""),
                    "domain": getattr(c, "domain", ""),
                    "path": getattr(c, "path", "/"),
                    "httpOnly": getattr(c, "http_only", getattr(c, "httpOnly", False)),
                    "secure": getattr(c, "secure", False),
                    "sameSite": getattr(c, "same_site", getattr(c, "sameSite", "")),
                }
        except Exception:
            continue

        domain_lower = (info.get("domain") or "").lower().lstrip(".")
        if any(
            domain_lower == d or domain_lower.endswith("." + d)
            for d in COOKIE_DOMAINS
        ):
            cookies.append(info)

    return cookies


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _safe_filename(email):
    return email.replace("@", "_at_").replace("/", "_").replace("\\", "_")


def _write_json_atomic(filepath, data):
    """先写 .tmp 再 rename，防止半写入。"""
    tmp = filepath + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filepath)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise
    return True


def _append_dedup_txt(filepath, line):
    """追加一行到文本文件，同 email 不重复。"""
    email_key = line.split("----")[0].strip().lower()
    existing = set()
    if os.path.isfile(filepath):
        with open(filepath, encoding="utf-8") as f:
            for existing_line in f:
                existing_line = existing_line.strip()
                if existing_line and not existing_line.startswith("#"):
                    existing.add(existing_line.split("----")[0].strip().lower())
    if email_key in existing:
        return False
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return True


def _extract_graph_via_page(page, email, password, proxy=None):
    """Use the registered browser session and PKCE to obtain a Graph refresh token."""
    import base64
    import hashlib
    import random
    import requests
    import secrets
    import string
    import time
    import urllib.parse

    CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
    REDIRECT_URI = "http://localhost"
    SCOPE = "offline_access https://graph.microsoft.com/Mail.Read"
    TENANT = "common"
    TOKEN_URL = "https://login.microsoftonline.com/{}/oauth2/v2.0/token".format(TENANT)

    _code_verifier = "".join(
        secrets.choice(string.ascii_letters + string.digits + "-._~")
        for _ in range(128)
    )
    _code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(_code_verifier.encode("utf-8")).digest()
    ).decode("ascii").rstrip("=")

    auth_url = (
        "https://login.microsoftonline.com/{}/oauth2/v2.0/authorize"
        "?client_id={}&response_type=code"
        "&redirect_uri={}&scope={}&response_mode=query"
        "&code_challenge={}&code_challenge_method=S256"
    ).format(
        TENANT,
        CLIENT_ID,
        urllib.parse.quote(REDIRECT_URI, safe=""),
        urllib.parse.quote(SCOPE, safe=""),
        _code_challenge,
    )

    captured = {"url": None}
    intercept_started = False

    def _capture_redirect(req):
        try:
            url = req.url or ""
            if url.startswith(REDIRECT_URI) and "code=" in url:
                captured["url"] = url
                print("[getAccountData] page OAuth: intercepted authorization code redirect")
        except Exception as exc:
            print("[getAccountData] page OAuth intercept handler error: {}: {}".format(
                type(exc).__name__, exc
            ))
        finally:
            try:
                if not req.handled:
                    req.continue_request()
            except Exception as exc:
                print("[getAccountData] page OAuth intercept continue error: {}: {}".format(
                    type(exc).__name__, exc
                ))

    try:
        page.intercept.start_requests(_capture_redirect)
        intercept_started = True
        page.get(auth_url, wait="complete")
        page.wait(random.uniform(1.0, 2.5))

        # The registration browser session is already authenticated. Do not
        # re-enter credentials; only grant consent when Microsoft asks for it.
        # Both browser polling phases share one monotonic 30-second deadline.
        _deadline = time.monotonic() + 30.0
        while time.monotonic() < _deadline:
            if captured["url"]:
                break
            skip_btn = page.ele('#iShowSkip', timeout=1)
            if skip_btn:
                print("[getAccountData] page OAuth: proofs/Add -> skip")
                skip_btn.click_self()
                page.wait(random.uniform(1.5, 3.0))
                continue
            consent_btn = page.ele('[data-testid="appConsentPrimaryButton"]', timeout=1)
            if consent_btn:
                consent_btn.click_self()
                page.wait(random.uniform(1.5, 3.0))
                continue
            page.wait(1.0)

        redirect_url = captured["url"]
        if intercept_started:
            try:
                page.intercept.stop()
            except Exception as exc:
                print("[getAccountData] page OAuth intercept stop error: {}: {}".format(
                    type(exc).__name__, exc
                ))
            intercept_started = False

        # Keep page.url as a fallback for BiDi/browser combinations that do
        # not surface this top-level redirect through interception.
        if not redirect_url:
            print("[getAccountData] page OAuth: intercept timed out; falling back to page.url")
            while time.monotonic() < _deadline:
                url = page.url or ""
                if "localhost" in url and "code=" in url:
                    redirect_url = url
                    break
                page.wait(1.0)

        if not redirect_url:
            print("[getAccountData] page OAuth: timed out waiting for code")
            return None

        parsed = urllib.parse.urlparse(redirect_url)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if not code:
            print("[getAccountData] page OAuth: redirect did not contain a code")
            return None

        print("[getAccountData] page OAuth: got authorization code")
        token_payload = {
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": _code_verifier,
        }
        request_kwargs = {"timeout": 15}
        if proxy:
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}
        token_resp = requests.post(TOKEN_URL, data=token_payload, **request_kwargs)
        body = token_resp.json()

        if body.get("refresh_token"):
            print("[getAccountData] page OAuth: refresh_token OK")
            return {
                "refresh_token": body["refresh_token"],
                "access_token": body.get("access_token", ""),
                "client_id": CLIENT_ID,
                "expires_in": body.get("expires_in"),
            }

        err = body.get("error_description", body.get("error", "unknown"))
        print("[getAccountData] page OAuth token error: {}".format(err[:150]))
        return None

    except Exception as exc:
        print("[getAccountData] page OAuth failed: {}: {}".format(type(exc).__name__, exc))
        return None
    finally:
        if intercept_started:
            try:
                page.intercept.stop()
            except Exception:
                pass


def _extract_graph_via_http(email, password, proxy=None, attempts=3):
    """按 reg-factory 的 3 次退避策略提取 Graph refresh token（HTTP 方式，作为回退）。"""
    # 方案5：临时把 reg-factory 模块全局的 requests 换成 SafeRedirectSession
    # 版，使 localhost callback 不被 requests 自动 follow（否则经 Kookeey
    # 代理发 localhost 会 ProxyError，code 拿不到）。串行执行无需锁；finally
    # restore 保证不泄漏。并发场景需加锁。
    _orig_requests = reg_factory_module.__dict__.get("requests")
    _fake_requests = _patched_requests_module()
    reg_factory_module.__dict__["requests"] = _fake_requests
    try:
        for attempt in range(attempts):
            try:
                # NOTE: reg-factory's get_graph_token() does not accept a proxy
                # parameter. We pass the proxy via environment variables, which is
                # safe in serial execution but would need explicit session-level
                # config for concurrent use. The finally block clears the vars.
                if proxy:
                    os.environ["HTTP_PROXY"] = str(proxy)
                    os.environ["HTTPS_PROXY"] = str(proxy)
                graph = get_graph_token(email, password)
            except Exception as exc:
                graph = None
                print("[getAccountData] HTTP graph attempt {}/{} error: {}: {}".format(
                    attempt + 1, attempts, type(exc).__name__, exc
                ))
            finally:
                if proxy:
                    os.environ.pop("HTTP_PROXY", None)
                    os.environ.pop("HTTPS_PROXY", None)

            if graph and graph.get("refresh_token"):
                return graph

            if attempt < attempts - 1:
                print("[getAccountData] HTTP graph attempt {}/{} missing; retrying.".format(
                    attempt + 1, attempts
                ))
                time.sleep(3 * (attempt + 1))

        print("[getAccountData] HTTP graph token missing after {} attempts.".format(attempts))
        return None
    finally:
        if _orig_requests is not None:
            reg_factory_module.__dict__["requests"] = _orig_requests
        else:
            reg_factory_module.__dict__.pop("requests", None)


def _extract_graph_for_account(page, email, password, proxy=None):
    """HTTP-first, with page OAuth as a bounded browser-session fallback."""
    result = _extract_graph_via_http(email, password, proxy=proxy)
    if result and result.get("refresh_token"):
        return result
    print("[getAccountData] HTTP failed, falling back to page OAuth...")
    return _extract_graph_via_page(page, email, password, proxy=proxy)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def save_account_data(page, email, password, proxy=None, output_dir=None):
    """保存注册成功的 Outlook 账号数据。

    Args:
        page:       ruyiPage FirefoxPage 实例
        email:      Outlook 邮箱地址
        password:   注册密码
        output_dir: 输出根目录，默认 None 使用本文件旁的 _outlook_pool/
        proxy:      Optional Graph-token HTTP(S) proxy; defaults to None.

    Returns:
        dict: {"ok": bool, "email": str, "has_graph_token": bool,
               "record_file": str or None, "pool_dir": str}
    """
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_outlook_pool"
        )

    pool_dir = output_dir
    os.makedirs(pool_dir, exist_ok=True)

    # 1. Graph token：page OAuth 优先 → HTTP 回退（先提取，后导出 cookie）
    graph = _extract_graph_for_account(page, email, password, proxy=proxy)
    has_token = bool(graph and graph.get("refresh_token"))
    print("[getAccountData] graph token: {}".format("OK" if has_token else "MISSING"))

    # 2. Cookie（page OAuth 可能新增/更新 Microsoft cookie，token 后导出）
    cookies = _export_cookies(page)
    print("[getAccountData] exported {} microsoft-related cookies".format(len(cookies)))

    # 3. 构造记录
    ts = datetime.now(timezone.utc).astimezone().isoformat()
    record = {
        "email": email,
        "password": password,
        "refresh_token": graph.get("refresh_token", "") if graph else "",
        "client_id": graph.get("client_id", "") if graph else "",
        "graph": graph or {},
        "outlook_cookies": cookies,
        "source": "ruyipage-email",
        "registration_proxy_strategy": proxy or "direct",
        "ts": ts,
    }

    safe_email = _safe_filename(email)
    record_file = None

    if has_token:
        fname = "{}_{}.json".format(
            datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18], safe_email
        )
        dst = os.path.join(pool_dir, fname)
        _write_json_atomic(dst, record)
        record_file = dst

        emails_path = os.path.normpath(os.path.join(pool_dir, "..", "emails.txt"))
        line = "{}----{}----{}----{}".format(
            email, password, graph.get("refresh_token", ""), graph.get("client_id", "")
        )
        _append_dedup_txt(emails_path, line)
        print("[getAccountData] saved to {} and emails.txt".format(dst))
    else:
        no_graph_path = os.path.normpath(os.path.join(pool_dir, "..", "outlook_no_graph.txt"))
        with open(no_graph_path, "a", encoding="utf-8") as f:
            f.write("{}----{}\n".format(email, password))
        print("[getAccountData] saved to outlook_no_graph.txt (no Graph RT)")

        pending_dir = os.path.join(pool_dir, ".pending")
        os.makedirs(pending_dir, exist_ok=True)
        pending_file = os.path.join(pending_dir, "{}.json".format(safe_email))
        pending_data = dict(record)
        pending_data["_no_token_reason"] = "graph token missing after 3 attempts"
        pending_data["_saved_at"] = ts
        _write_json_atomic(pending_file, pending_data)
        record_file = pending_file
        print("[getAccountData] pending record saved to {}".format(pending_file))

    return {
        "ok": has_token,
        "email": email,
        "has_graph_token": has_token,
        "record_file": record_file,
        "pool_dir": pool_dir,
    }
