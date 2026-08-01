# 04 - 执行进度

## 当前状态(2026-08-01)

**全部阶段完成** ✅ 修复计划闭环。实测验证通过(run_batch 1/1 + revive 2/3)。

**已完成并 commit**:

| commit | 阶段 | 文件 | insertions/deletions |
|---|---|---|---|
| `ca4466d` | 阶段0 + 阶段2 | px_captcha.py, waits.py, getAccountData.py, FirefoxOptions.py, run_batch.py | +142 / -31 |
| `fb248be` | 阶段1 | getAccountData.py | +106 / -74 |
| `46719b0` | 阶段1补丁(proofs/Add Skip) | getAccountData.py | +6 / -0 |
| `f9948df` | 文档 | md/ 7 文件 | +413 / -0 |
| `57d1f2d` | 阶段3 P0 | revive_pending.py | +234 / -0 |
| `8dc3cf0` | 文档同步 | md/02,03,04 | +15 / -25 |
| `1a545aa` | 阶段4 | 删 get_token.py + md/02,04 | +15 / -10 |
| `4a0bd8b` | 阶段5(实测优化) | getAccountData.py | +9 / -8 |

## 阶段进度

### ✅ 阶段0(PX 验证 + token 成功语义)— 完成(ca4466d)
- #4 PX 重试死循环 → continue
- timeout 方案甲(retry 重试,timeout 不重试)
- D stale-frame 保护(93/104/114/68-73)
- 方案B:wait_for_px_captcha_iframe stale 闭合
- 成功语义:无 token 不计成功

### ✅ 阶段2(批量调度韧性)— 完成(并入 ca4466d)
- deque 替换 idx 错位
- _classify_exception 三分类
- 方案乙:PX 失败代理增 streak

### ✅ 阶段1(token 机制)— 完成(fb248be + 46719b0)
- intercept 捕获 code(替代 page.url 轮询)
- 不填密码只 consent(复用会话)
- token exchange 走注册代理
- fallback page.url 轮询保底
- 补丁:proofs/Add Skip(`#iShowSkip`)

### ✅ 阶段3 P0(revive_pending)— 完成(57d1f2d)
- 新独立脚本 revive_pending.py(HTTP-only)
- fresh sticky Kookeey 代理 + 原子幂等落盘 + attempt 限制 + 幂等 rerun
- 实测:17 个 .pending,--limit 3 跑出 2 成功 1 Abuse 封号

### ✅ 阶段4(清理)— 完成(1a545aa)
- 删 get_token.py(Playwright API + 读不存在的 config.json,从未接入,全仓无引用)

### ✅ 阶段5(实测优化)— 完成(4a0bd8b)
- HTTP-first 调换优先级(实测 HTTP 更稳更快)
- page-OAuth 共享 monotonic 30s deadline
- Abuse/proofs reason 降级(reg-factory 无可识别信号)

## 实测验证结果(2026-08-01)

### run_batch BATCH_SIZE=1
- 尝试#1 jjeoue3c7ataxi:PX 3 次 retry 全失败,streak 1/3 保留(方案乙+PX 重试生效)
- 尝试#2 ddosbhdpftyjy4:PX passed → page-OAuth intercept 失效(问题A)→ fallback page.url 超时 → HTTP 回退 → proofs skip→denied(问题B)→ retry consent → OK → ✅ 成功 1/1
- 修复点全验证:#4 重试、stale 不冒泡、成功语义、异常分类、deque、proofs/Add skip

### revive_pending --limit 3
- e3acoxutgdza6i:HTTP attempt1 proofs skip→denied,attempt2 consent→OK(成功)
- fnvtsj5jozbnt:同上(成功)
- fcibxnlap7ozob:3 次 Abuse 封号(失败)
- summary: success:2, failed:1

## 下一步(可选,非代码工作)

修复计划全部闭环。剩余:
1. 跑 `revive_pending.py` 全量复活剩余 .pending(14 个)
2. 跑 `run_batch.py` 验证阶段5 后 token 成功率 + 速度提升
3. `.env` BATCH_SIZE 测试时改成了 1,实测后改回 5

## 已知运行时问题(非阻断,见 03-issues.md)

- 问题 A(intercept 在 PX 后失效):阶段5 已用 HTTP-first 规避
- 问题 B(OAuth 首次必失败):reg-factory 既有行为,降级
- 问题 C(Abuse 封号):不可救,attempt 限制已处理
