"""串行批量注册 Outlook 账号。"""
import time
from FirefoxOptions import run_once


# ── 配置 ──
BATCH_SIZE = 2                 # 本次注册数量
PROXY = "http://127.0.0.1:7897"
WAIT_BETWEEN = 10              # 两次注册间隔（秒）
FIREFOX_QUIT_WAIT = 3          # quit 后等 Firefox 释放端口

for i in range(1, BATCH_SIZE + 1):
    print(f"\n--- 第 {i}/{BATCH_SIZE} 次 ---")
    ok, record = run_once(proxy=PROXY)
    print(f"  结果: {'OK ' + (record or '') if ok else 'FAIL'}")

    if i < BATCH_SIZE:
        time.sleep(FIREFOX_QUIT_WAIT)
        print(f"  等待 {WAIT_BETWEEN} 秒...")
        time.sleep(WAIT_BETWEEN)

print(f"\n完成 {BATCH_SIZE} 次")
