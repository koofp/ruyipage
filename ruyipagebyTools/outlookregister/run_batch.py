"""串行批量注册 Outlook 账号——节点轮换，代理异常自动移除。"""
import os
import sys
import time
from FirefoxOptions import run_once
from datetime import datetime

# 日志
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "_logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("batch_%Y%m%d_%H%M%S.log"))


class _Tee:
    def __init__(self, filepath):
        self.console = sys.stdout
        self.file = open(filepath, "a", encoding="utf-8", buffering=1)

    def write(self, text):
        self.console.write(text)
        self.file.write(text)

    def flush(self):
        self.console.flush()
        self.file.flush()


sys.stdout = _Tee(LOG_FILE)
sys.stderr = sys.stdout
print(f"日志: {LOG_FILE}")

# ── 加载 .env（必须在读取 os.environ 之前）──
_ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
if os.path.isfile(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ── 配置 ──（.env 已加载）
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))
WAIT_BETWEEN = int(os.environ.get("WAIT_BETWEEN", "10"))
FIREFOX_QUIT_WAIT = int(os.environ.get("FIREFOX_QUIT_WAIT", "3"))
PROXY_FILE = os.path.join(SCRIPT_DIR, "proxies_ok.txt")
PROXY_MODEL = os.environ.get("PROXY_MODEL", "false").strip().lower() in ("true", "1", "yes")
AUTO_COUNTRY = os.environ.get("AUTO_COUNTRY", "JP").strip().upper()

# ── 代理来源 ──
proxies = []
if PROXY_MODEL:
    from common.kookeey_api import KookeeyAPI
    _access_id = os.environ.get("KOOKEY_ACCESS_ID", "")
    _token = os.environ.get("KOOKEY_TOKEN", "")
    if not _access_id or not _token:
        print("❌ PROXY_MODEL=true 但 KOOKEY_ACCESS_ID/KOOKEY_TOKEN 未在 .env 中设置")
        sys.exit(1)
    api = KookeeyAPI(_access_id, _token)
    proxies = api.generate_extraction_proxies(
        count=BATCH_SIZE * 2,
        country_code=AUTO_COUNTRY,
        sticky=False,
        protocol="http",
    )
    print(f"✅ API 生成 {len(proxies)} 个 {AUTO_COUNTRY} 代理")
else:
    try:
        with open(PROXY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)
    except FileNotFoundError:
        proxies = []

if not proxies:
    print("❌ 没有可用代理" + ("" if PROXY_MODEL else f"，请检查 {PROXY_FILE}"))
    sys.exit(1)

print(f"加载 {len(proxies)} 个代理")

successes = 0
attempt = 0
max_attempts = BATCH_SIZE * 3

while successes < BATCH_SIZE and proxies and attempt < max_attempts:
    attempt += 1
    idx = (attempt - 1) % len(proxies)
    proxy = proxies[idx]
    print(f"\n--- 尝试 #{attempt}（成功 {successes}/{BATCH_SIZE}）节点[{(attempt-1)%len(proxies)}]==>{proxy} ---")

    # ── Clash 预切 ──
    from urllib.parse import urlparse as _urlparse
    try:
        _parsed = _urlparse(proxy)
        _pwd = _parsed.password or ""
        _parts = _pwd.split("-")
        _country = None
        for _part in _parts:
            if len(_part) == 2 and _part.isalpha() and _part.isupper():
                _country = _part
                break
    except Exception:
        _country = None

    if _country:
        try:
            from clash_helper import match_country_node
            match_country_node(_country)
        except Exception as _e:
            print(f"  Clash pre-select: {type(_e).__name__}: {_e}")

    try:
        ok, record = run_once(proxy=proxy)
    except Exception as exc:
        print(f"  ❌ 异常: {type(exc).__name__}: {str(exc)[:120]}")
        print(f"  移除代理: {proxy[:60]}...")
        if proxy in proxies:
            proxies.remove(proxy)
        if not PROXY_MODEL:
            with open(PROXY_FILE, "w", encoding="utf-8") as f:
                for p in proxies:
                    f.write(p + "\n")
        if not proxies:
            print("❌ 所有代理已用完，停止")
            break
        print(f"  剩余代理: {len(proxies)}")
        time.sleep(FIREFOX_QUIT_WAIT)
        continue

    if ok:
        successes += 1
        print(f"  ✅ 成功 {successes}/{BATCH_SIZE}")
    else:
        print(f"  ❌ PX 或注册失败，不保存")

    if successes < BATCH_SIZE and proxies:
        time.sleep(FIREFOX_QUIT_WAIT)
        time.sleep(WAIT_BETWEEN)

print(f"\n{'='*50}")
print(f"  完成: 成功 {successes}/{BATCH_SIZE}，总尝试 {attempt}")
print(f"  剩余代理: {len(proxies)}")
print(f"{'='*50}")
