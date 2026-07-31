# 04 - 执行进度

## 当前状态(2026-07-31)

**正在做**:阶段1 补丁(proofs/Add Skip 处理)— 已派写码 Codex(任务 019fb826),待其实现 + 审核员复审。

**已完成并 commit**:

| commit | 阶段 | 文件 | insertions/deletions |
|---|---|---|---|
| `ca4466d` | 阶段0 + 阶段2 | px_captcha.py, waits.py, getAccountData.py, FirefoxOptions.py, run_batch.py | +142 / -31 |
| `fb248be` | 阶段1 | getAccountData.py | +106 / -74 |

## 阶段进度

### ✅ 阶段0(PX 验证 + token 成功语义)— 完成
- #4 PX 重试死循环 → continue
- timeout 方案甲(retry 重试,timeout 不重试)
- D stale-frame 保护(93/104/114/68-73)
- 方案B:wait_for_px_captcha_iframe stale 闭合
- 成功语义:无 token 不计成功

### ✅ 阶段2(批量调度韧性)— 完成(并入 ca4466d)
- deque 替换 idx 错位
- _classify_exception 三分类
- 方案乙:PX 失败代理增 streak

### ✅ 阶段1(token 机制)— 完成(fb248be)
- intercept 捕获 code(替代 page.url 轮询)
- 不填密码只 consent(复用会话)
- token exchange 走注册代理
- fallback page.url 轮询保底

### 🔄 阶段1 补丁(proofs/Add)— 进行中
- 任务 019fb826,派给写码 Codex
- Skip 按钮选择器 `#iShowSkip`(用户提供)
- 改 getAccountData.py:194-202,加 proofs/Add 检测在 consent 前

### ⏳ 阶段3(revive_pending)— 待开始
- 新独立脚本 revive_pending.py
- HTTP 先 + 重新登录版 intercept 兜底
- 依赖阶段1 补丁完成(proofs/Add 修复后 page-OAuth 才能用)

### ⏳ 阶段4(清理)— 待开始
- 删 get_token.py

## 下一步

1. 等阶段1 补丁实现 → 审核员复审 → 我复核 → commit
2. 启动阶段3 revive_pending
3. 阶段4 删 get_token.py

## 待用户定的开放问题

- **scope 升级?** `Mail.Read` → `offline_access Mail.ReadWrite Mail.Send User.Read`(取决于下游用途,待用户定)
