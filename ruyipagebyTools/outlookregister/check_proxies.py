"""读取 proxies.txt，多线程并发测试能否访问 signup.live.com，输出可用代理。"""
import os
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

PROXY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies.txt")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies_ok.txt")
TEST_URL = "https://signup.live.com/"
TIMEOUT = 10
WORKERS = 20                    # 并发线程数（不过量，避免代理服务器限流）

_write_lock = threading.Lock()


def check_one(proxy_url):
    """TCP 连通性测试 — 只测 host:port 是否可达。"""
    try:
        parsed = urlparse(proxy_url)
        sock = socket.create_connection(
            (parsed.hostname, parsed.port), timeout=TIMEOUT)
        sock.close()
        return True
    except Exception:
        return False


# ── 读取 ──
proxies = []
with open(PROXY_FILE, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            proxies.append(line)

if not proxies:
    print(f"❌ {PROXY_FILE} 中没有代理")
    sys.exit(1)

# ── 清除旧结果文件 ──
if os.path.exists(OUTPUT_FILE):
    os.remove(OUTPUT_FILE)

# ── 并发检测 ──
socket.setdefaulttimeout(TIMEOUT)
print(f"检测 {len(proxies)} 个代理（{TEST_URL}，超时 {TIMEOUT}s，{WORKERS} 线程）\n")

ok_count = 0
done_count = 0


def _append_result(proxy_url):
    """线程安全：实时追加一条可用代理到输出文件。"""
    with _write_lock:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(proxy_url + "\n")


with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    future_map = {pool.submit(check_one, p): p for p in proxies}

    for future in as_completed(future_map):
        proxy = future_map[future]
        ok = future.result()
        done_count += 1

        if ok:
            ok_count += 1
            _append_result(proxy)

        # 进度：每 50 个或最后一个打印
        if done_count % 50 == 0 or done_count == len(proxies):
            print(f"  进度 {done_count}/{len(proxies)}  可用 {ok_count}")

# ── 收尾 ──
if ok_count:
    print(f"\n✅ {ok_count}/{len(proxies)} 可用 → {OUTPUT_FILE}")
else:
    print(f"\n❌ 0/{len(proxies)} 可用")
    sys.exit(1)
