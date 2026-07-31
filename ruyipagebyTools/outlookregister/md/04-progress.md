# 04 - 执行进度

## 当前状态(2026-07-31)

**下一步**:阶段3 revive_pending.py 复活 .pending(HTTP + 浏览器兜底)。

**已完成并 commit**:

| commit | 阶段 | 文件 | insertions/deletions |
|---|---|---|---|
| `ca4466d` | 阶段0 + 阶段2 | px_captcha.py, waits.py, getAccountData.py, FirefoxOptions.py, run_batch.py | +142 / -31 |
| `fb248be` | 阶段1 | getAccountData.py | +106 / -74 |
| `46719b0` | 阶段1补丁(proofs/Add Skip) | getAccountData.py | +6 / -0 |
| `f9948df` | 文档 | md/ 7 文件 | +413 / -0 |

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

### ✅ 阶段1 补丁(proofs/Add)— 完成(46719b0)
- 加 proofs/Add 检测在 consent 前,点 `#iShowSkip` 跳过(对应 reg-factory action=Skip)
- page-OAuth 流程机制完整:authorize→登录→proofs/Add(Skip)→consent→redirect(intercept 抓 code)→token exchange(走代理)
- 真实效果待批跑实测

### ⏳ 阶段3(revive_pending)— 待开始
- 新独立脚本 revive_pending.py
- HTTP 先 + 重新登录版 intercept 兜底(复用 proofs/Add 处理)
- 17 个 .pending 存量资产

### ⏳ 阶段4(清理)— 待开始
- 删 get_token.py(Playwright API + 读不存在的 config.json,从未接入)

## 下一步

1. 启动阶段3 revive_pending(HTTP + 浏览器兜底)
2. 阶段4 删 get_token.py

## 待用户定的开放问题

- **scope 升级?** `Mail.Read` → `offline_access Mail.ReadWrite Mail.Send User.Read`(取决于下游用途,待用户定)
