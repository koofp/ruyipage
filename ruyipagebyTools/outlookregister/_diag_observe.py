"""一次性诊断驱动：只跑指定的 3 个 .pending 账号，复用 revive_pending 的
_revive_one / _make_proxy_provider。观测层(getAccountData)会把每个 attempt 的
完整 HTTP 轨迹写到 _outlook_pool/.observe/{email}.log。

用法: python _diag_observe.py
跑完看 _outlook_pool/.observe/ 下 3 个 .log。
"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from revive_pending import _load_env, _make_proxy_provider, _revive_one, PENDING_DIR

# 挑定的 3 个账号（att=0，诊断价值最高）
TARGETS = [
    "oeyr2cmtagrhk_at_outlook.com.json",   # 08-02 3x proofs-denied -> H2 vs H1
    "rhdubgslftxash_at_outlook.com.json",  # 解封后强制绑邮箱 -> H1 确认
    "c5dcuyhycznlf_at_outlook.com.json",   # 08-02 代理超时+SSL+proofs 混合 -> W4 vs 逻辑
]


def main():
    _load_env(SCRIPT_DIR / ".env")
    fresh_proxy = _make_proxy_provider()
    counts = {}
    for name in TARGETS:
        path = PENDING_DIR / name
        if not path.is_file():
            print("[diag] {} 不存在，跳过".format(name))
            continue
        print("\n" + "=" * 70)
        print("[diag] === {} ===".format(name))
        print("=" * 70)
        outcome = _revive_one(path, fresh_proxy)
        counts[outcome] = counts.get(outcome, 0) + 1
    print("\n[diag] summary: {}".format(counts))
    print("[diag] 观测日志在: {}".format(SCRIPT_DIR / "_outlook_pool" / ".observe"))


if __name__ == "__main__":
    main()
