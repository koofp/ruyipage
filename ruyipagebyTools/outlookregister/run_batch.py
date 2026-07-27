"""串行批量注册 Outlook 账号——节点轮换，代理异常自动移除。"""
import os
import sys
import time
from FirefoxOptions import run_once

BATCH_SIZE = 5               # 需要成功注册的个数
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(SCRIPT_DIR, "proxies_ok.txt")
WAIT_BETWEEN = 10
FIREFOX_QUIT_WAIT = 3

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
