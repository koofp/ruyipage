"""Clash node selector: match country code to lowest-latency GLOBAL node."""
import json
import os
import urllib.parse
import urllib.request

# 加载上级目录下的 .env 文件
# 优先当前目录，回退到 project 根目录
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                _key = _key.strip()
                _val = _val.strip()
                if _key and _val and _key not in os.environ:
                    os.environ[_key] = _val

_CLASH_API = os.environ.get("CLASH_API", "http://127.0.0.1:9097")
_CLASH_GROUP = os.environ.get("CLASH_GROUP", "GLOBAL")
_CLASH_SECRET = os.environ.get("CLASH_SECRET", "")
_TIMEOUT = 8
_SPECIAL_NAMES = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}
_GROUP_TYPES = ("selector", "fallback", "urltest", "loadbalance")
_FAKE_HINTS = (
    "剩余流量", "剩余", "到期", "重置", "套餐", "官网", "客服",
    "自动选择", "故障转移", "Traffic", "Expire", "Reset",
)

_COUNTRY_KEYWORDS = {
    "JP": ["日本", "Japan", "🇯🇵", "Tokyo", "Osaka"],
    "US": ["美国", "USA", "🇺🇸", "United States", "Los Angeles", "New York",
           "Seattle", "Chicago", "Dallas", "Miami", "San Jose", "Silicon Valley"],
    "GB": ["英国", "UK", "🇬🇧", "London", "United Kingdom"],
    "HK": ["香港", "🇭🇰", "Hong Kong"],
    "SG": ["新加坡", "🇸🇬", "Singapore"],
    "KR": ["韩国", "🇰🇷", "Korea", "Seoul"],
    "TW": ["台湾", "🇹🇼", "Taiwan", "Taipei"],
    "DE": ["德国", "🇩🇪", "Germany", "Frankfurt"],
    "NL": ["荷兰", "🇳🇱", "Netherlands", "Amsterdam"],
    "AU": ["澳大利亚", "🇦🇺", "Australia", "Sydney"],
    "IN": ["印度", "🇮🇳", "India", "Mumbai", "Delhi"],
    "CA": ["加拿大", "🇨🇦", "Canada", "Toronto", "Vancouver"],
    "FR": ["法国", "🇫🇷", "France", "Paris"],
    "BR": ["巴西", "🇧🇷", "Brazil", "Sao Paulo"],
}


def _req(path, method="GET", body=None, timeout=_TIMEOUT):
    headers = {"Content-Type": "application/json"}
    if _CLASH_SECRET:
        headers["Authorization"] = f"Bearer {_CLASH_SECRET}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(f"{_CLASH_API}{path}", data=data,
                                  headers=headers, method=method)
    if method == "DELETE":
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read()
        except Exception as exc:
            if "401" in str(exc):
                print("[clash] DELETE /connections returned 401 (auth required)")
        return None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if not raw:
            return None
        return json.loads(raw)


def match_country_node(target_country_code):
    """在 Clash GLOBAL 组中找目标国家延迟最低的节点并切换。

    target_country_code: 2-letter ISO code like "JP", "US", "GB".
    Returns dict: {ok, node, latency_ms, country} or {ok: False, reason}.
    """
    country_code = target_country_code.upper().strip()

    # 1) list all proxies to filter groups from terminal nodes
    all_info = _req("/proxies")
    all_proxies = all_info.get("proxies", {})

    # 2) list nodes in target group, exclude special names & groups & fake hints
    group_info = all_proxies.get(_CLASH_GROUP) or {}
    all_nodes = group_info.get("all") or []
    nodes = []
    for n in all_nodes:
        if n in _SPECIAL_NAMES:
            continue
        if any(h in n for h in _FAKE_HINTS):
            continue
        # exclude sub-groups (selector/fallback/url-test etc)
        node_type = (all_proxies.get(n) or {}).get("type") or ""
        if node_type.lower() in _GROUP_TYPES:
            continue
        nodes.append(n)

    # 3) match by country
    keywords = _COUNTRY_KEYWORDS.get(country_code, [country_code])
    candidates = []
    for node in nodes:
        node_upper = node.upper()
        for kw in keywords:
            if kw.upper() in node_upper:
                candidates.append(node)
                break

    if not candidates:
        return {"ok": False, "reason": f"no node for {country_code} (keywords: {keywords})"}

    # 4) probe latency for each candidate
    best_node, best_latency = None, None
    for node in candidates:
        try:
            q = urllib.parse.urlencode({"url": "http://www.gstatic.com/generate_204",
                                         "timeout": 3000})
            d = _req(f"/proxies/{urllib.parse.quote(node, safe='')}/delay?{q}")
            latency = (d or {}).get("delay")
        except Exception:
            latency = None
        if latency is not None and (best_latency is None or latency < best_latency):
            best_node, best_latency = node, latency

    if best_node is None:
        return {"ok": False, "reason": f"all {len(candidates)} candidates for {country_code} timed out"}

    # 5) switch group to best node
    _req(f"/proxies/{urllib.parse.quote(_CLASH_GROUP, safe='')}", method="PUT",
         body={"name": best_node})
    _req("/connections", method="DELETE")

    print(f"[clash] switched {_CLASH_GROUP} -> {best_node!r} ({best_latency}ms) for {country_code}")
    return {"ok": True, "node": best_node, "latency_ms": best_latency, "country": country_code}
