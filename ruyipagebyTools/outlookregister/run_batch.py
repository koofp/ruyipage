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
# 
batch_size = os.environ.get("BATCH_SIZE", 7)
wait_between = os.environ.get("WAIT_BETWEEN", 10)
firefox_quit_wait = os.environ.get("FIREFOX_QUIT_WAIT", 5)

BATCH_SIZE = batch_size              # 需要成功注册的个数
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(SCRIPT_DIR, "proxies_ok.txt")
WAIT_BETWEEN = wait_between   # 每次注册完等待时间
FIREFOX_QUIT_WAIT = firefox_quit_wait # 退出火狐浏览器等待时间

# 从已过滤文件读取可用代理
proxies = []
try:
    with open(PROXY_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line)
except FileNotFoundError:
    proxies = []

if not proxies:
    print(f"❌ {PROXY_FILE} 为空或不存在，请先运行 check_proxies.py")
    sys.exit(1)

print(f"加载 {len(proxies)} 个代理")

successes = 0
attempt = 0
max_attempts = BATCH_SIZE * 3          # 防无限循环（每个成功允许 2 次失败）

while successes < BATCH_SIZE and proxies and attempt < max_attempts:
    attempt += 1
    idx = (attempt - 1) % len(proxies)
    proxy = proxies[idx]
    print(f"\n--- 尝试 #{attempt}（成功 {successes}/{BATCH_SIZE}）节点[{idx}==>{proxy}] ---")

    # ── Clash 预切：代理国家匹配延迟最低节点 ──
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
        # 重写代理文件
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
