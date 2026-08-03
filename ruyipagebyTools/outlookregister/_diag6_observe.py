"""扩大诊断驱动：跑 6 个 .pending，验证方案A 止损效果 + 看 denied 占比。
复用 revive_pending._revive_one / _make_proxy_provider。观测层写 .observe/。
跑完看 _outlook_pool/.observe/ 下 .log + 主日志。
"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from revive_pending import _load_env, _make_proxy_provider, _revive_one, PENDING_DIR

# 6 个：2 个 att=0 全新诊断 + oeyr2cmtagrhk(应被 A 标 terminal)
# + rhdubgslftxash(上次也 denied) + 2 个 att=0 的
TARGETS = [
    "oeyr2cmtagrhk_at_outlook.com.json",   # att=1, 上次 3x denied -> 验证 A: terminal-skip 或再次 denied
    "rhdubgslftxash_at_outlook.com.json",  # att=1, 上次 3x denied -> 验证 A
    "lbdbcapmwplt_at_outlook.com.json",    # att=0 全新
    "mmtakyxe5leex_at_outlook.com.json",   # att=0 全新
    "slwiem6wrqaw_at_outlook.com.json",    # att=0 全新
    "vdwzcyqyamgvut_at_outlook.com.json",  # att=0 全新
]


def main():
    _load_env(SCRIPT_DIR / ".env")
    fresh_proxy = _make_proxy_provider()
    counts = {}
    for name in TARGETS:
        path = PENDING_DIR / name
        if not path.is_file():
            print("[diag6] {} 不存在，跳过".format(name))
            continue
        print("\n" + "=" * 70)
        print("[diag6] === {} ===".format(name))
        print("=" * 70)
        outcome = _revive_one(path, fresh_proxy)
        counts[outcome] = counts.get(outcome, 0) + 1
    print("\n[diag6] summary: {}".format(counts))
    print("[diag6] 观测日志在: {}".format(SCRIPT_DIR / "_outlook_pool" / ".observe"))


if __name__ == "__main__":
    main()
