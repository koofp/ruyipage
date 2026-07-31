# 05 - token 提取路径分析

## 三条 token 路径

| 路径 | 机制 | 依赖 | 信任度 | 适用场景 |
|---|---|---|:---:|---|
| **page-OAuth(intercept)** | 浏览器内 OAuth,intercept 捕 code | 活浏览器会话(注册当场) | 高 | 注册成功当场取 token |
| **HTTP 回退**(reg-factory) | requests 模拟 MS 登录页,POST 凭据跟 redirect 抓 code | 纯 email/password + 代理 | 中 | 任意时刻(含 .pending) |
| **开浏览器重新登录+intercept** | 起浏览器→登录→intercept 抓 code | email/password + 代理 | 高 | .pending 复活兜底 |

## 微软 OAuth 真实流程(关键!)

```
authorize
  → 登录页(注册当场会话在,可能不出现)
  → proofs/Add(要求绑定关联邮箱/安全验证)  ← 关键卡点!
  → consent(应用授权页)
  → redirect http://localhost/?code=...
  → token exchange(POST /token)
```

## proofs/Add 根因(日志实证)

- **reg-factory HTTP 版**:extract_graph_tokens.py:180-196 用 `action=Skip` 处理 proofs/Add(解析 form、提交 Skip)→ **成功**(日志 `[#0] OK! refresh_token=yes` 全是 HTTP)。
- **`_extract_graph_via_page`**:只等 `appConsentPrimaryButton`(consent 页),**没处理 proofs/Add** → 卡在 proofs/Add → 30 轮超时 → `timed out waiting for code`(日志 4 次)→ **从没成功过**。
- proofs/Add 出现在 consent **之前**,不处理就到不了 consent、到不了 redirect。

## get_token.py vs _extract_graph_via_page

| | get_token.py | _extract_graph_via_page |
|---|---|---|
| 处理 proofs/Add | ❌ 没有 | ❌ 没有(阶段1补丁将修) |
| 处理 consent | ✅ appConsentPrimaryButton | ✅ 同 |
| 抓 code | page.on("request") Playwright | intercept ruyipage |
| 能否成功 | ❌ 不会(卡 proofs/Add) | ❌ 不会(卡 proofs/Add) |

**结论**:两者都有**同一个缺陷——没处理 proofs/Add**。不是抓 code 方式差别导致失败,是两者本身都缺 proofs/Add 处理,根本不会成功。阶段1 修的 intercept+走代理是对的,但没补 proofs/Add,所以修了等于没修。

## get_token.py 的 config.json(参考)

```json
{
  "oauth2": {
    "enable_oauth2": false,       // 当前死代码
    "client_id": "",              // 空
    "Scopes": ["offline_access", "Mail.ReadWrite", "Mail.Send", "User.Read"]  // 比我们多
  }
}
```

- get_token.py 当前是死代码(enable_oauth2=false + client_id 空)。
- **Scopes 比我们多**:`Mail.ReadWrite` + `Mail.Send` + `User.Read`(我们只有 `Mail.Read`)。取决于下游用途:只读邮件 → Mail.Read 够;要发邮件 → 加 Mail.Send。

## Skip 按钮选择器(用户提供,已确认)

proofs/Add 页 Skip 按钮:
```html
<a id="iShowSkip" href="#" class="secondary-text">暂时跳过(7 天后必须输入)</a>
```
浏览器版用 `page.ele('#iShowSkip').click_self()` 点它跳过(对应 HTTP 版 action=Skip)。

## 修复方向

`_extract_graph_via_page` 等代码循环(194-202)加 proofs/Add 检测(放 consent 前):
```python
skip_btn = page.ele('#iShowSkip', timeout=1)
if skip_btn:
    skip_btn.click_self()  # 跳过绑定邮箱
    continue
consent_btn = page.ele('[data-testid="appConsentPrimaryButton"]', timeout=1)
...
```
