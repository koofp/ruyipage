# 03 - 确定性问题清单

> 已校准(经 Codex 独立验证 + 日志实证 + 库源码核对)。按真实严重度排序。文档只记确定性结论。

## 已修复(阶段0/1/2 + 阶段1补丁,commit `ca4466d` + `fb248be` + `46719b0`)

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

---

## 不成立 / 已澄清(避免重复判错)

| 曾误判 | 真实情况 | 证据 |
|---|---|---|
| "HTTP 回退链路断(reg-factory 不存在)" | reg-factory 在 `ai-email/reg-factory/`,可用 | glob 确认 |
| "page-OAuth 是可用主体" | 反了:真正产出 token 的是 HTTP 回退,page-OAuth 从没成功 | 日志 `[#0] OK` 全是 HTTP |
| ".pending 是 page-OAuth 脆导致" | 主因是 proofs/Add 没处理 + 代理失败 | 日志 timed out + ProxyError |
| "page-OAuth 自相矛盾会重复登录加风控" | 部分错:page-OAuth 先跑(复用会话),失败才 HTTP 兜底,串行不重复 | getAccountData:309-323 |
| "localhost 无监听致 page.url 拿不到 code" | 被实测推翻:无 listener 时 page.url 仍含 code | Codex 实测 + firefox_base.py:3404 |
| "cookie 被 OAuth 中间页干扰(问题3)" | 不成立:cookie 是整个 jar 按域名过滤,不是当前页 | _export_cookies:41-83 |
| "代码强制走 Clash 而非注册代理" | 推翻:HTTP_PROXY/HTTPS_PROXY 环境变量被 trust_env 读取 | requests merge_environment_settings |
| "no such frame 冒泡误杀代理(问题5 现存)" | 当前 HEAD 已被 4992a43 修复(get_visible_px_iframe 加保护);但 93/104/114/68-73/61 仍漏,阶段0 补齐 | git show 4992a43 |

## 存疑(非确定性,不作为修复前提)

| # | 问题 | 定性 |
|---|---|---|
| 2 | HTTP 提 token 出口 IP 与注册 IP 不一致触发风控 | 存疑:Kookeey sticky=False 无 IP 校验,无法由代码/日志证明 |

## 不在工作范围(兄弟仓库 reg-factory)

| # | 问题 | 说明 |
|---|---|---|
| A | HTTP auto-redirect 到 localhost 致 ProxyError | 根因在 reg-factory/extract_graph_tokens.py:58/111/122 的 allow_redirects=True,但 reg-factory 不可改。.pending 主因之一 |
