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
import threading
import time
import types
import urllib.parse
from contextvars import ContextVar
from datetime import datetime, timezone
import requests
from extract_graph_tokens import get_graph_token, reg_factory_module


# ---------------------------------------------------------------------------
# 观测层 + localhost redirect 安全 Session（方案5 同机制）
# ---------------------------------------------------------------------------
# ContextVar 标记当前正在提取哪个账号 —— reg-factory 每次 attempt 内的
# 所有 HTTP 请求都被 SafeRedirectSession 捕获，记到 .observe/{email}.log。
# 纯加日志，不改 token 逻辑，不改 reg-factory 源码（用方案5 的 globals 注入）。
_OBSERVE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_outlook_pool", ".observe"
)
_current_email: ContextVar = ContextVar("_current_email_for_observe", default="")
_obs_lock = threading.Lock()

# 终态信号（方案5 同机制，ContextVar 在 reg-factory 的 request 内被 set，
# 调用方在 get_graph_token 返回后读取）。一次 attempt 内被覆写多次无妨，
# 取最后值。_extract_graph_via_http 每 attempt reset，跨 attempt 收集后判定。
# _last_classification：一次 _extract_graph_via_http 调用结束后的终态分类，
# 供 save_account_data / revive_pending 读取（denied-3x / abuse → terminal）。
_terminal_reason: ContextVar = ContextVar("_terminal_reason", default=None)
_last_classification: ContextVar = ContextVar("_last_classification", default=None)


def get_last_classification():
    """返回最近一次 _extract_graph_via_http 的终态分类，供落盘/跨run止损用。

    结构：{"terminal": bool,
           "type": "success"|"denied"|"abuse"|"dead-line"|"retryable",
           "denied_count": int, "net_streak": int, "attempts": int}。
    dead-line 只是同一代理线路连续失败的观测值，非账号终态；terminal=True
    仅表示 denied-3x 或 Abuse，revive 应跳过不再重试。
    """
    return _last_classification.get()


def _observe_log(line):
    """把一行观测记录同时打到 stdout 和 .observe/{email}.log。"""
    email = _current_email.get()
    try:
        print(line)
    except Exception:
        pass
    if not email:
        return
    try:
        with _obs_lock:
            os.makedirs(_OBSERVE_DIR, exist_ok=True)
            safe = email.replace("/", "_").replace("\\", "_")
            path = os.path.join(_OBSERVE_DIR, "{}.log".format(safe))
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


class SafeRedirectSession(requests.Session):
    """覆写 get_redirect_target：当重定向目标是 localhost callback（含
    code=/error=）时返回 None，让 requests 不自动 follow——把原始 302
    response 返回给调用方（reg-factory 的 128-150 手动 loop 据此提 code）。

    背景：reg-factory 的 credentials POST（:111）等用 allow_redirects=True，
    微软 redirect 到 http://localhost/?code=... 时 requests 自动 follow，经
    Kookeey 代理发 localhost 请求会 ProxyError，code 明明在 URL 却拿不到。
    本类只在 localhost callback 时不 follow，其他 redirect 正常放行。

    观测层（方案5 同机制，纯加日志）：覆写 request() 记录 reg-factory 发出的
    每条请求 method+url，以及 requests 自动 follow 的每跳 redirect（resp.history
    里的 3xx + Location），失败时记异常。所有记录走 _observe_log 落盘到
    .observe/{email}.log，供事后判定 H1(必须绑)/H2(概率)/H3(丢状态)/I2(Abuse)/
    W4(代理)。仅记日志，不干预请求本身。"""

    def request(self, method, url, *args, **kwargs):
        method_upper = str(method).upper()
        try:
            resp = super().request(method, url, *args, **kwargs)
        except Exception as exc:
            _observe_log("      [REQ-ERR] {} {} -> {}: {}".format(
                method_upper, _short_url(url), type(exc).__name__, str(exc)[:200]
            ))
            # 代理/网络失败分类为 retryable（除非 body 已明确 abuse，见下）
            if _terminal_reason.get() is None:
                _terminal_reason.set("retryable-network")
            raise
        # 记录 requests 自动 follow 的每跳 redirect（resp.history 是 3xx 序列）
        for hop in getattr(resp, "history", []) or []:
            loc = hop.headers.get("Location", "")
            _observe_log("      [REDIR] {} {} -> {} {}".format(
                hop.status_code, _short_url(hop.url), hop.status_code,
                ("Location=" + _short_url(loc)) if loc else "(no Location)"
            ))
        _observe_log("      [RESP] {} {} -> {}".format(
            method_upper, _short_url(url), resp.status_code
        ))
        # Abuse 页分类（proofs/Add 后回到 Abuse，不可救）
        url_lower = (url or "").lower()
        if "account.live.com/abuse" in url_lower:
            _terminal_reason.set("abuse")
            _observe_log("      [TERMINAL] Abuse 页（微软封号，不可救）")
        return resp

    def get_redirect_target(self, resp):
        target = super().get_redirect_target(resp)
        if target:
            host = (urllib.parse.urlparse(target).hostname or "").lower()
            if host in ("localhost", "127.0.0.1") and ("code=" in target or "error=" in target):
                # localhost callback：不 follow，把原始 302 返回给 reg-factory 手动 loop
                _observe_log("      [CALLBACK-STOP] 302 Location=localhost?code=/error= -> 不 follow(方案5)")
                # 解析 localhost?error=... 的 error 值（如 access_denied）
                if "error=" in target:
                    try:
                        params = urllib.parse.parse_qs(
                            urllib.parse.urlparse(target).query
                        )
                        err = (params.get("error", [None]) or [None])[0]
                        if err:
                            _terminal_reason.set("denied:{}".format(err))
                            _observe_log("      [TERMINAL] localhost?error={}（微软账号态拒绝）".format(err))
                    except Exception:
                        _terminal_reason.set("denied:unknown-error")
                return None
        return target


def _short_url(url):
    """把超长 query（epct/epctrc 等几 KB 字段）截短，日志可读。"""
    if not url:
        return "(empty)"
    s = str(url)
    if len(s) <= 160:
        return s
    try:
        parsed = urllib.parse.urlparse(s)
    except Exception:
        return s[:160] + "...(trunc)"
    q = parsed.query
    if len(q) > 80:
        q = q[:80] + "...(trunc {}B)".format(len(q))
    base = "{}://{}{}".format(parsed.scheme, parsed.netloc, parsed.path)
    if q:
        base += "?" + q
    if parsed.fragment:
        base += "#" + parsed.fragment[:40]
    return base


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
    _token = None
    _tr_token = None
    _deny_streak = 0
    _net_streak = 0
    _last_terminal = None
    try:
        _token = _current_email.set(email)
        _tr_token = _terminal_reason.set(None)
        _observe_log(
            "  ── HTTP attempt 链路开始: {} proxy={} ──".format(email, proxy or "(no proxy)")
        )
        for attempt in range(attempts):
            # 每 attempt reset 终态信号（reg-factory 的 request 内会 set）
            _terminal_reason.set(None)
            _observe_log("  ── attempt {}/{} ──".format(attempt + 1, attempts))
            try:
                # NOTE: reg-factory's get_graph_token() does not accept a proxy
                # parameter. We pass the proxy via environment variables, which is
                # safe in serial execution but would need explicit session-level
                # config for concurrent use. The finally block clears the vars.
                if proxy:
                    _http_proxy = str(proxy)
                    # requests/urllib3 用 socks5h 表示 SOCKS5 代理侧 DNS；旧 socks5
                    # 地址统一升级，避免本地解析后出现 TLS EOF。
                    if _http_proxy.lower().startswith("socks5://"):
                        _http_proxy = "socks5h://" + _http_proxy[len("socks5://"):]
                    os.environ["HTTP_PROXY"] = _http_proxy
                    os.environ["HTTPS_PROXY"] = _http_proxy
                graph = get_graph_token(email, password)
            except Exception as exc:
                graph = None
                _observe_log("  [getAccountData] HTTP graph attempt {}/{} error: {}: {}".format(
                    attempt + 1, attempts, type(exc).__name__, exc
                ))
            finally:
                if proxy:
                    os.environ.pop("HTTP_PROXY", None)
                    os.environ.pop("HTTPS_PROXY", None)

            # 读 attempt 终态信号（denied:<err> / abuse / retryable-network / None）
            _terminal = _terminal_reason.get()
            _observe_log("  [getAccountData] attempt {} result: {}{}".format(
                attempt + 1,
                "refresh_token=yes" if (graph and graph.get("refresh_token")) else "missing",
                (" terminal={}".format(_terminal)) if _terminal else ""
            ))
            if graph and graph.get("refresh_token"):
                _last_classification.set({"terminal": False, "type": "success",
                                          "attempts": attempt + 1, "denied_count": _deny_streak,
                                          "net_streak": _net_streak})
                return graph

            # 终态分类止损（方案A）：denied/abuse 是微软账号态决定，重试不变。
            # attempt1 3x 全 denied 的账号加更多 attempt 也一样 denied。
            if _terminal == "abuse":
                _last_terminal = "abuse"
                _observe_log("  [getAccountData] terminal: Abuse（封号，停止重试）")
                break
            if _terminal and str(_terminal).startswith("denied"):
                _deny_streak += 1
                _net_streak = 0  # 账号态信号优先，网络连续失败重新计数
                _last_terminal = _terminal
                if _deny_streak >= 3:
                    _observe_log("  [getAccountData] terminal: denied×{}（微软账号态拒绝，停止重试）".format(_deny_streak))
                    break
                _observe_log("  [getAccountData] denied streak {}/3（继续重试，微软两步式 consent 概率）".format(_deny_streak))
            elif _terminal == "retryable-network":
                # 网络错误只累计线路连续失败，不打断已观察到的 denied 计数
                _net_streak += 1
                if _net_streak >= 3:
                    _observe_log("  [getAccountData] retryable-network streak {}（线路连续失败，停止重试）".format(_net_streak))
                    break
            else:
                # 无信号（missing 但无 localhost denied）会打断连续网络失败
                _net_streak = 0

            if attempt < attempts - 1:
                _observe_log("  [getAccountData] HTTP graph attempt {}/{} missing; retrying.".format(
                    attempt + 1, attempts
                ))
                time.sleep(3 * (attempt + 1))

        _net_dead = _net_streak >= 3
        _classification = {
            # dead-line 是代理线路观测值，账号本身仍可换代理重试。
            "terminal": (_last_terminal == "abuse"
                         or (_last_terminal and str(_last_terminal).startswith("denied")
                             and _deny_streak >= 3)),
            "type": ("abuse" if _last_terminal == "abuse"
                     else ("denied" if (_last_terminal and str(_last_terminal).startswith("denied")
                                        and _deny_streak >= 3)
                           else ("dead-line" if _net_dead else "retryable"))),
            "attempts": attempt + 1,
            "denied_count": _deny_streak,
            "net_streak": _net_streak,
            "last_terminal": _last_terminal,
        }
        _last_classification.set(_classification)
        _observe_log("  [getAccountData] HTTP graph token missing after {} attempts. classification={}".format(
            attempts, _classification
        ))
        return None
    finally:
        if _tr_token is not None:
            _terminal_reason.reset(_tr_token)
        if _token is not None:
            _current_email.reset(_token)
        if _orig_requests is not None:
            reg_factory_module.__dict__["requests"] = _orig_requests
        else:
            reg_factory_module.__dict__.pop("requests", None)


def _extract_graph_for_account(page, email, password, proxy=None):
    """纯 HTTP 提取 Graph refresh token（与旧版 881721d 完全一致）。

    控制变量法结论：旧版只调 get_graph_token（reg-factory 纯 HTTP），成功率高。
    我们加 page-OAuth 兜底后成功率下降 —— 兜底会触发浏览器内完整 OAuth
    （真实 PX + 登录 + 绑定/信息收集），风控与失败率上升。故去掉 page-OAuth，
    token 路径回到纯 HTTP（方案5 仅规避 localhost follow，不改变 HTTP 主路径）。
    page 参数保留仅用于签名兼容（save_account_data 仍传），实际不用于 token。
    """
    return _extract_graph_via_http(email, password, proxy=proxy)


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

    # 1. Graph token：纯 HTTP（与旧版 881721d 一致；无 page-OAuth 兜底）
    graph = _extract_graph_for_account(page, email, password, proxy=proxy)
    has_token = bool(graph and graph.get("refresh_token"))
    print("[getAccountData] graph token: {}".format("OK" if has_token else "MISSING"))

    # 2. Cookie（token 后导出，保留注册会话的 Microsoft cookie）
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
        # 终态分类（方案A）：区分"不可救(terminal)"vs"可重试(retryable)"
        classification = get_last_classification() or {}
        terminal = classification.get("terminal", False)
        classification_type = classification.get("type")
        if terminal and classification_type == "dead-line":
            pending_data["_no_token_reason"] = (
                "terminal: dead-line (代理线路连续失败，非账号态)")
        elif terminal:
            pending_data["_no_token_reason"] = (
                "terminal: {} (微软账号态决定，不可重试)".format(
                    classification_type))
        else:
            pending_data["_no_token_reason"] = (
                "graph token missing (retryable: 代理/网络/概率)")
        pending_data["_terminal"] = terminal
        pending_data["_classification"] = classification
        pending_data["_saved_at"] = ts
        _write_json_atomic(pending_file, pending_data)
        record_file = pending_file
        print("[getAccountData] pending record saved{}: {}".format(
            " (terminal:{})".format(classification.get("type")) if terminal else "", pending_file
        ))

    return {
        "ok": has_token,
        "email": email,
        "has_graph_token": has_token,
        "record_file": record_file,
        "pool_dir": pool_dir,
    }
