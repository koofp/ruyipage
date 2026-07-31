# 01 - outlookregister 项目描述

## 项目本质

基于自研库 **ruyipage**(Firefox + WebDriver BiDi,自带过检测内核)构建的 **Outlook 邮箱批量自动注册 + Graph Token 提取系统**。

端到端目标:输入一批代理 → 自动注册 Outlook 账号 → 突破 PX 人机验证 → 提取 Microsoft Graph refresh_token → 落盘成可复用的账号资产。

## 目录结构

```
ruyipage/                        ← 底层库(Firefox + WebDriver BiDi,v1.2.54)
├── ruyipage/                    ← 核心库代码
├── examples/                    ← 使用示例(40_1 验证了 intercept API)
└── ruyipagebyTools/
    └── outlookregister/         ← 本模块
        ├── run_batch.py          ← 批量入口
        ├── FirefoxOptions.py     ← 单次注册入口(run_once)
        ├── config.py             ← 浏览器配置
        ├── utils.py              ← 随机数据(邮箱/密码/姓名/生日)
        ├── register_flow.py      ← 注册表单填写
        ├── px_captcha.py         ← PX 验证码总调度
        ├── waits.py              ← iframe 等待/结果轮询
        ├── px_probe.py           ← PX 探测 JS
        ├── win32_mouse.py        ← Win32 原生鼠标按压
        ├── clash_helper.py       ← Clash 节点选择
        ├── getAccountData.py     ← 账号数据保存 + token 提取
        ├── get_token.py          ← 游离参考代码(Playwright API,未接入)
        ├── extract_graph_tokens.py ← 桥接 reg-factory
        ├── check_proxies.py      ← 代理检测
        ├── common/kookeey_api.py ← Kookeey 代理 API
        ├── _outlook_pool/        ← 成功账号(带 token)
        ├── _outlook_pool/.pending/ ← 半成品(注册成功但无 token)
        ├── _logs/                ← 批跑日志
        ├── emails.txt            ← 成功账号一行式记录
        ├── outlook_no_graph.txt  ← 无 token 的 email/password
        └── .env                  ← 配置
```

## 完整工作流

```
run_batch.py(批量调度,deque+异常分类)
  └─ FirefoxOptions.run_once(proxy)        ← 单次注册
       ├─ config.create_page()              启动 Firefox + 代理 + 打开 signup.live.com
       ├─ register_flow.fill_form()         邮箱→密码→生日→姓名 表单自动化
       ├─ px_captcha.handle_captcha()       PX 验证总调度
       │    ├─ waits: 等待 #human iframe
       │    ├─ waits: 等待 #px-captcha iframe(stale-frame 保护)
       │    ├─ px_probe: JS 探测挑战元素 + hitbox
       │    ├─ win32_mouse: Win32 SendInput OS 级长按 12-15s
       │    └─ waits: 轮询 PX 结果(passed/retry/timeout)
       └─ getAccountData.save_account_data()  账号落盘
            ├─ _extract_graph_via_page()   ← 阶段1:intercept 捕 code + 走代理 + proofs/Add Skip
            └─ _extract_graph_via_http()   ← reg-factory HTTP 回退
```

## 关键设计

- **PX 突破**:`win32_mouse.py` 用 `SendInput` OS 级按压,绕过 BiDi 跨域 iframe 限制;`is_done` 回调进度条走满提前松手。
- **Clash 智能路由**:从代理 URL 密码段解析国家码,调 Clash API 选该国家最低延迟节点。
- **Kookeey 提取模式代理**:API 生成 `gate.kookeey.info:1000` 带国家/session 的代理 URL。
- **Graph Token 双轨**:page-OAuth(注册当场会话,信任度高)优先,HTTP 回退。
- **PKCE OAuth2**:`client_id=9e5f94bc-e8a4-4e73-b8be-63364c29d753`,scope=`offline_access Mail.Read`,redirect=`http://localhost`。

## 产出数据格式

成功账号 JSON(`_outlook_pool/*.json`):
- `email`, `password`, `refresh_token`, `client_id`
- `graph`(子字段含 email/password/refresh_token/client_id)
- `outlook_cookies`(Microsoft 域 Cookie)
- `registration_proxy_strategy`, `ts`

## 配置(.env 实际值)

```
PROXY_MODEL=true          Kookeey API 自动生成代理
AUTO_COUNTRY=JP           日本节点
BATCH_SIZE=5              每批目标成功 5 个(已改为只计拿 token 的)
CLASH_API=http://127.0.0.1:9097  CLASH_SECRET=sk-hxs2019
KOOKEY_ACCESS_ID=4419993
```

## reg-factory(兄弟仓库,不在本模块工作范围)

位于 `D:\...\ai-email\reg-factory\`,有独立 .venv 和 .git。本模块复用其 `extract_graph_tokens.py` 的 `get_graph_token(email, password)`(纯 HTTP OAuth,含 proofs/Add 的 action=Skip 处理)。**不可修改 reg-factory**。
