# 03 - 确定性问题清单

> 已校准(经 Codex 独立验证 + 日志实证 + 库源码核对)。按真实严重度排序。文档只记确定性结论。

## 已修复(阶段0/1/2/3/4/5)

| # | 问题 | 位置 | 修复 commit |
|---|---|---|---|
| 4 | PX 3 次重试被 155 行 return False 截断(4992a43 误引入) | px_captcha.py | ca4466d |
| timeout | retry→continue,timeout→return False(方案甲) | px_captcha.py | ca4466d |
| D | px_captcha 对 humanCaptchaIframe 裸调用无 stale 保护(93/104/114/68-73) | px_captcha.py | ca4466d |
| B(方案B) | wait_for_px_captcha_iframe 内 run_js 无保护,stale 冒泡 | waits.py + px_captcha.py:61 | ca4466d |
| B(成功语义) | 无 Graph token 仍计成功,占用 BATCH_SIZE | getAccountData + FirefoxOptions | ca4466d |
| 6 | run_batch except Exception 无脑删代理(含可重试异常) | run_batch.py | ca4466d |
| 7 | idx=(attempt-1)%len(proxies) 删代理后错位 | run_batch.py | ca4466d |
| 1 | page-OAuth 用 page.url 轮询抓 code(脆)+ 裸 urlopen 不走代理 | getAccountData | fb248be |
| proofs/Add | _extract_graph_via_page 没处理 proofs/Add 绑定页,卡死从没成功 | getAccountData.py:194-202 | 46719b0 |
| 3 P0 | .pending 账号无 token,无活会话,需复活 | revive_pending.py(新) | 57d1f2d |
| 4 清理 | get_token.py 游离参考代码(Playwright API,未接入) | 删除 get_token.py | 1a545aa |
| 5 | page-OAuth 空耗 70s + 实测 HTTP 更稳,优先级反了 | getAccountData | 4a0bd8b |

---

## 实测发现的运行时问题(已分析)

### 问题 A:intercept 在 PX 后失效
**日志证据**:run_batch 尝试#2,PX passed 后:
```
[getAccountData] page OAuth intercept continue error: BiDiError: no such request: Blocked request with id 77-... not found
[getAccountData] page OAuth: intercept timed out; falling back to page.url
[getAccountData] page OAuth: timed out waiting for code
```

**根因(库源码实证 interceptor.py:1398-1429 + 702-705)**:
- `continue_request()` 先置 `_handled=True` 再发 BiDi continueRequest;
- BiDi 报 `no such request`(请求被 PX 阻断/移除),但 `req.handled` 已 True;
- `_on_intercept:1428` 的 `if not req.handled` 为 False → 框架兜底 continue 不执行;
- localhost 导航请求没进 handler(日志无 "intercepted authorization code redirect")→ PX Blocked 机制在 beforeRequestSent 之前拦了,或 active intercept 与 PX/signup 有 race。

**处理**:阶段5 调换 HTTP-first 规避——不依赖 page-OAuth 主路径,HTTP 更稳更快,page-OAuth 留作有界兜底。

### 问题 B:OAuth 首次必失败(两步式 consent)
**日志证据**:revive e3acoxutgdza6i / fnvtsj5jozbnt 均同模式:
```
attempt1: proofs/Add skip → "OAuth error: user has denied access to the scope" 失败
attempt2: accepting Consent/Update → got auth code → OK
```

**根因**:微软两步式 consent,proofs skip 后返回 denied,第二次到 Consent/Update 才同意。这是 reg-factory HTTP 既有行为,非我们引入。

**处理**:降级不改(reg-factory get_graph_token 对 proofs-denied 返回 None,无可识别 reason 信号,wrapper 无法区分,需改 reg-factory 本体——不在范围)。

### 问题 C:Abuse 封号
**日志证据**:revive fcibxnlap7ozob 3 次 `FAIL: stuck at account.live.com/Abuse?...&lmif=40&ab` (status=200)。

**根因**:微软风控封号,不可救。

**处理**:revive attempt 限制(3 次)已处理(留 .pending 不再重试)。**降级**:Abuse 早识别跳过未实现——reg-factory get_graph_token 对 Abuse 也返回 None,无 URL/异常/reason 可识别信号(全 catch Exception→None),wrapper 收到 None 无法区分 Abuse vs 其他失败。

---

## 不成立 / 已澄清(避免重复判错)

| 曾误判 | 真实情况 | 证据 |
|---|---|---|
| "HTTP 回退链路断(reg-factory 不存在)" | reg-factory 在 `ai-email/reg-factory/`,可用 | glob 确认 |
| "page-OAuth 是可用主体" | 反了:真正产出 token 的是 HTTP 回退,page-OAuth 从没成功 | 日志 `[#0] OK` 全是 HTTP;阶段5 已反转 HTTP-first |
| ".pending 是 page-OAuth 脆导致" | 主因是 proofs/Add 没处理 + 代理失效 | 日志 timed out + ProxyError |
| "page-OAuth 自相矛盾会重复登录加风控" | 部分错:page-OAuth 先跑(复用会话),失败才 HTTP 兜底,串行不重复 | getAccountData:309-323 |
| "localhost 无监听致 page.url 拿不到 code" | 被实测推翻:无 listener 时 page.url 仍含 code | Codex 实测 + firefox_base.py:3404 |
| "cookie 被 OAuth 中间页干扰(问题3)" | 不成立:cookie 是整个 jar 按域名过滤 | _export_cookies:41-83 |
| "代码强制走 Clash 而非注册代理" | 推翻:HTTP_PROXY/HTTPS_PROXY 环境变量被 trust_env 读取 | requests merge_environment_settings |
| "no such frame 冒泡误杀代理(问题5 现存)" | 当前 HEAD 已被 4992a43 修复;93/104/114/68-73/61 阶段0 补齐 | git show 4992a43 |

## 存疑(非确定性)

| # | 问题 | 定性 |
|---|---|---|
| 2 | HTTP 提 token 出口 IP 与注册 IP 不一致触发风控 | 存疑:Kookeey sticky=False 无 IP 校验,无法证明 |

## 不在工作范围(兄弟仓库 reg-factory)

| # | 问题 | 说明 |
|---|---|---|
| A | HTTP auto-redirect 到 localhost 致 ProxyError | reg-factory/extract_graph_tokens.py:58/111/122 allow_redirects=True,但 reg-factory 不可改。**方案5(2ffd2d5)已在 wrapper 侧 SafeRedirectSession 规避** |
| Abuse 早识别 | reg-factory 对 Abuse 返回 None 无信号 | 需改 reg-factory 本体,不在范围。**观测层已识别 Abuse URL(方案A),止损不重试** |
| proofs reason | reg-factory proofs skip→denied 无 reason 信号 | 同上。**观测层已解析 localhost?error=access_denied(方案A),止损不重试** |

---

## 方案5 闭环实证(2026-08-02 诊断)

- **机制验证**:SafeRedirectSession 的 `[CALLBACK-STOP] 不 follow(方案5)` 在每个 attempt 都正常触发(`.observe/*.log`)。
- **端到端实证**:`c5dcuyhycznlf@outlook.com` attempt2 成功拿 token(`refresh_token` 417 字符,落 pool + emails.txt,pending 已清)。**这是方案5 commit(2ffd2d5)之后第一次端到端成功**,确认方案5 没有把事搞坏。
- **观测层**:`getAccountData` 加 SafeRedirectSession.request() 记录 reg-factory 每条 HTTP(method+url+status+redirect 轨迹),落 `.observe/{email}.log`。ContextVar 标当前账号。纯加日志,不改 token 逻辑,不改 reg-factory。

## 根因判定:H1/H2/H3 → **微软账号态分叉(非代码)**

观测轨迹(3 账号逐 attempt 切分)推翻了之前三个假设,定到真因:

| 账号 | attempt 轨迹 | 终态 | 判定 |
|---|---|---|---|
| c5dcuyhycznlf | proofs→Skip→302→**Consent/Update→ucaction=Yes→code**→换 token 时代理 RemoteDisconnected | attempt2 成功 | 能到 Consent 就稳 |
| oeyr2cmtagrhk | proofs→Skip→302→**oauth20_authorize?error=access_denied**(回 authorize 带 denied),3 次全 | terminal denied | 微软账号态拒绝 |
| rhdubgslftxash | 同 oeyr2cmtagrhk(3 次全 denied) | terminal denied | 同上 |

**关键分叉点 = proofs/Add 之后落到哪:**
- **Consent/Update** → 拿 code → 换 token(成功,代理偶断可重试覆盖)
- **oauth20_authorize?error=access_denied** → denied(失败,微软账号态决定,重试不变)

**H1(必须绑邮箱)被推翻**:rhdubgslftxash 的 Skip POST 返回 302(正常被接受),不是停在 proofs/Add。它失败原因和 oeyr2cmtagrhk 完全一样(denied),**不是"必须绑"导致卡死**。

**H2(概率)部分成立**:c5dcuyhycznlf attempt1 已拿 code,只代理偶断;attempt2 同流程成功。说明 denied 不是随机的(3 次全 denied = 账号态),Consent 类是稳的。

**H3(丢状态)被推翻**:不是 Session 丢 cookie,是微软账号态分叉。

## 方案A:终态分类止损(已实现)

- `SafeRedirectSession.get_redirect_target` 检测 `localhost?error=` 解析 error 值 → `_terminal_reason` ContextVar set `denied:access_denied`
- `request()` 检测 `account.live.com/Abuse` URL → set `abuse`
- `_extract_graph_via_http`:denied 连续 3 次 / abuse → break 不重试 + 带出 classification
- `save_account_data` / `revive_pending` 把 `_terminal=True` 写入 pending,下次 `terminal-skip` 不再重试

**效果**:denied/abuse 账号不浪费 attempt/代理;只对 retryable(代理偶断/网络)重试。

## 方案C:revive 本地代理 fallback(已实现)

- `revive_pending._make_proxy_provider` 代理优先级:Kookeey > `proxies_ok.txt`(本地轮转)> Clash 直连
- 绕开 Kookeey 站点不稳/SSL(W4),复用 run_batch 的 `PROXY_FILE`

## 真实天花板(基于这次数据)

- 能到 Consent 的账号 → 大概率成功(代理偶断可重试)
- proofs→denied 账号 → 不可救(微软账号态,重试无效,方案A 止损)
- .pending 池子是"微软不让过"子集,denied 可能占多数 → 真实成功率有限,非代码能提升
