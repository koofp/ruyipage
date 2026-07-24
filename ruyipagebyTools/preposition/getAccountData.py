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
from datetime import datetime, timezone
from extract_graph_tokens import get_graph_token

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


def _extract_graph_for_account(email, password, proxy=None, attempts=3):
    """按 reg-factory 的 3 次退避策略提取 Graph refresh token。"""
    for attempt in range(attempts):
        try:
            graph = get_graph_token(email, password, proxy=proxy)
        except Exception as exc:
            graph = None
            print("[getAccountData] graph token attempt {}/{} error: {}: {}".format(
                attempt + 1, attempts, type(exc).__name__, exc
            ))

        if graph and graph.get("refresh_token"):
            return graph

        if attempt < attempts - 1:
            print("[getAccountData] graph token attempt {}/{} missing; retrying.".format(
                attempt + 1, attempts
            ))
            time.sleep(3 * (attempt + 1))

    print("[getAccountData] graph token missing after {} attempts.".format(attempts))
    return None


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def save_account_data(page, email, password, output_dir=None, proxy=None):
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

    # 1. Cookie
    cookies = _export_cookies(page)
    print("[getAccountData] exported {} microsoft-related cookies".format(len(cookies)))

    # 2. Graph token
    graph = _extract_graph_for_account(email, password, proxy=proxy)
    has_token = bool(graph and graph.get("refresh_token"))
    print("[getAccountData] graph token: {}".format("OK" if has_token else "MISSING"))

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
        "ok": True,
        "email": email,
        "has_graph_token": has_token,
        "record_file": record_file,
        "pool_dir": pool_dir,
    }
