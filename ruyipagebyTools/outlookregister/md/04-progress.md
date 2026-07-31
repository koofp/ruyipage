# 04 - 执行进度

## 当前状态(2026-07-31)

**全部阶段完成** ✅ 修复计划闭环。剩余:真实批跑实测验证(待用户跑)。

**已完成并 commit**:

| commit | 阶段 | 文件 | insertions/deletions |
|---|---|---|---|
| `ca4466d` | 阶段0 + 阶段2 | px_captcha.py, waits.py, getAccountData.py, FirefoxOptions.py, run_batch.py | +142 / -31 |
| `fb248be` | 阶段1 | getAccountData.py | +106 / -74 |
| `46719b0` | 阶段1补丁(proofs/Add Skip) | getAccountData.py | +6 / -0 |
| `f9948df` | 文档 | md/ 7 文件 | +413 / -0 |
| `57d1f2d` | 阶段3 P0 | revive_pending.py | +234 / -0 |
| `8dc3cf0` | 文档同步 | md/02,03,04 | +15 / -25 |

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

### ✅ 阶段3 P0(revive_pending)— 完成(57d1f2d)
- 新独立脚本 revive_pending.py(HTTP-only)
- fresh sticky Kookeey 代理 + 原子幂等落盘 + attempt 限制 + 幀等 rerun
- 17 个 .pending 存量资产可复活

### ✅ 阶段4(清理)— 完成
- 删 get_token.py(Playwright API + 读不存在的 config.json,从未接入,全仓无引用)
- 其"重新登录+监听抓code"思路已被阶段1 intercept 吸收

## 下一步

修复计划全部闭环。剩余:
1. 真实批跑 `run_batch.py` 实测 PX 通过率 + token 成功率(阶段0/1/2 效果验证)
2. 跑 `revive_pending.py` 实测 .pending 复活率(阶段3 效果验证)
3. 若 page-OAuth intercept 抓不到导航 redirect(风险点1),fallback page.url 兜底;若 HTTP 对 .pending 某些账号不行,再考虑 P1 浏览器兜底

## 待用户定的开放问题

- **scope 升级?** `Mail.Read` → `offline_access Mail.ReadWrite Mail.Send User.Read`(取决于下游用途,待用户定)
