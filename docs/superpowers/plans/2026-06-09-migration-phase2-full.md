# 剩余脚本迁移计划（6 个功能块）

> 仅规划，不编码。按依赖关系排序，每个阶段独立可交付。

**迁移策略：** 全部采用 LegacyBridge 包装模式（与 Outlook/Gmail 相同），不重写业务逻辑。

---

## 依赖关系 → 迁移顺序

```
阶段 1（无依赖）         阶段 2（依赖阶段1）      阶段 3（依赖阶段2）
┌──────────────┐    ┌──────────────────┐    ┌────────────────┐
│ 邮箱中间件    │    │ Claude 注册       │    │ 多平台编排      │
│ common/      │ ←──│ ChatGPT 注册      │ ←──│ 端到端流程      │
│ mailbox      │    │ Grok 注册         │    │                │
└──────────────┘    └──────────────────┘    └────────────────┘
┌──────────────┐    ┌──────────────────┐
│ 下游集成      │    │ 运维工具          │
│ Token/导出    │    │ 解锁/循环/验证    │
└──────────────┘    └──────────────────┘
```

---

## 阶段 1A：邮箱中间件迁移

**文件：** common/mailbox.py (396行) + mailbox_broker.py (382行)
**迁移到：** services/shared/mailbox/

### 做什么

| 组件 | 新文件 | 来源函数 | 说明 |
|------|--------|---------|------|
| Graph API 客户端 | shared/mailbox/graph_client.py | `_get_access_token()` + `fetch_messages()` | 纯 HTTP，token 刷新 + 邮件拉取 |
| 验证码提取器 | shared/mailbox/code_extractor.py | `get_code_by_token()` | 从邮件正文提取 magic link 或 6位 code |
| 浏览器取码 | shared/mailbox/browser_fetcher.py | `get_code_outlook_pw()` | 浏览器登录 Outlook 取码（Graph API 失败时兜底） |
| Broker 服务 | shared/mailbox/broker.py | `mailbox_broker.py` 整体 | 并发锁 + aiohttp 共享取码服务 |

### 为什么先迁移这个

Claude/ChatGPT/Grok 注册都依赖邮箱取码。不迁移这个，后面 3 个注册 Flow 都无法独立工作。

### 测试策略

- GraphClient：mock HTTP 响应测试 token 刷新和邮件解析
- CodeExtractor：用固定 HTML 测试 magic link / code 正则提取
- BrowserFetcher：仅测试接口签名（真实测试需要 Outlook 账号）

---

## 阶段 1B：下游集成迁移

**文件：** 5 个脚本共 1033 行
**迁移到：** services/account_service/ 扩展 + services/shared/uploaders/

### 做什么

| 组件 | 新文件 | 来源 | 说明 |
|------|--------|------|------|
| Graph Token 提取 | shared/mailbox/graph_token_extractor.py | extract_graph_tokens.py (362行) | 纯 HTTP OAuth2 流程，批量提取 refresh_token |
| 导出格式扩展 | account_service/exporter.py (已有，扩展) | export_accounts.py (170行) | 添加 Chrome 扩展格式导出 |
| ChatGPT2API 导出 | shared/uploaders/chatgpt2api.py | export_chatgpt2api.py (178行) | POST 到 chatgpt2api 接口 |
| Token 上传 | shared/uploaders/token_uploader.py | upload_tokens.py (156行) | 上传到 CPA/SUB2API/webchat2api，幂等 |
| Codex OAuth | shared/uploaders/codex_oauth.py | oauth_codex.py (167行) | 用 Cookie 重登 → Codex OAuth → refresh_token |

### 依赖

- shared/uploaders/ 需要 common/session_export.py (462行) 和 common/uploaders.py (179行) 的功能
- 同时迁移这两个 common/ 模块

### 测试策略

- GraphTokenExtractor：mock OAuth 响应
- 各 Uploader：mock HTTP POST 验证幂等和错误处理

---

## 阶段 2A：Claude.ai 注册迁移

**文件：** register.py (4041行)
**迁移到：** services/worker/step_engine.py 新增 ClaudeRegistrationFlow

### 做什么

新增 `ClaudeRegistrationFlow`，4 步：

| 步骤 | execute_step 实现 | 调用的现有函数 |
|------|------------------|--------------|
| 1. Prepare email | LegacyBridge → `buy_outlook_email()` 或从邮箱池取 | register.py 中的邮箱准备逻辑 |
| 2. Browser login + magic link | LegacyBridge → `open_and_connect()` → 导航到 Claude 登录页 → `get_magic_link_by_token()` → 点击 link | register.py 的 Claude 登录流程 |
| 3. Phone verification | LegacyBridge → SMS Service 取号 → 填入手机号 → 轮询验证码 | register.py 的手机验证部分 |
| 4. Extract session + cleanup | 提取 Cookie/sessionKey → 保存 → teardown | register.py 的 Cookie 提取 |

### 关键依赖

- **阶段 1A 的邮箱中间件**：magic link 通过 Graph API 从 Outlook inbox 提取
- **SMS Service**：手机验证码通过新架构的 SMS Service 获取（已有 5 个适配器）
- **共享 browser_utils**：Stealth 注入（已迁移）

### 特殊处理

register.py 有 4041 行，但核心 Claude 注册流程约 800 行。其余是 Outlook 注册（已在 OutlookRegistrationFlow 中）、Replit 副线（可选）、辅助函数。只包装 Claude 相关函数。

---

## 阶段 2B：ChatGPT 注册迁移

**文件：** register_chatgpt.py (787行)
**迁移到：** services/worker/step_engine.py 新增 ChatGptRegistrationFlow

### 做什么

新增 `ChatGptRegistrationFlow`，5 步：

| 步骤 | 调用的现有函数 |
|------|--------------|
| 1. Prepare email | 从邮箱池取一个已注册的 Outlook 账号 |
| 2. Browser navigate + email submit | `register_one()` 前半段：打开 chatgpt.com → 填邮箱 → 提交 |
| 3. Email verification | `common/mailbox.get_code_by_token()` 提取 6 位验证码 → 填入 |
| 4. Onboarding | `handle_onboarding()` 填名字/生日 |
| 5. Save cookies + import | `common/cookies.save()` + `import_chatgpt2api()` |

### 关键依赖

- 阶段 1A 邮箱中间件（取 6 位 code）
- 阶段 1B 的 chatgpt2api 上传（可选，注册成功即时导入）

---

## 阶段 2C：Grok 注册迁移

**文件：** register_grok.py (859行)
**迁移到：** services/worker/step_engine.py 新增 GrokRegistrationFlow

### 做什么

新增 `GrokRegistrationFlow`，5 步：

| 步骤 | 调用的现有函数 |
|------|--------------|
| 1. Prepare email + proxy | 从邮箱池取号 + Clash 节点切换 |
| 2. Browser navigate + Turnstile | `register_one()` → `pass_page_challenge()` + `ensure_turnstile()` |
| 3. Email submit + verification | 填邮箱 → `mailbox.get_code_by_token()` 取 6 位 code |
| 4. Complete registration | 完成注册表单 |
| 5. Save cookies + upload | 保存 Cookie → 可选上传 webchat2api |

### 特殊处理

Grok 的核心难点是 **Cloudflare 全页拦截**：
- 必须走代理（需要 proxy_switch 模块）
- Turnstile 挑战需要打码（CapSolver/EZ-Captcha，已迁移验证码框架）
- 渲染等待很长（代理加载 30-40s）

---

## 阶段 2D：运维工具迁移

**文件：** 4 个脚本共 1276 行
**迁移到：** services/gateway/ 新增路由 + services/worker/tasks.py 新增任务

### 做什么

| 工具 | 迁移方式 | 新位置 |
|------|---------|--------|
| unlock_outlook.py (604行) | Celery 异步任务 + Gateway API | `POST /tools/unlock-outlook` → Worker task |
| outlook_reg_loop.py (399行) | Celery Beat 定时任务 | `beat_schedule["outlook-reg-loop"]` + Worker task |
| validate_keys.py (163行) | Gateway API | `POST /tools/validate-keys` → Worker task |
| activate_plus.py (110行) | Gateway API | `POST /tools/activate-plus` |

### 前端集成

- 设置页面新增「运维工具」Tab
- 一键触发：解锁、验证、激活
- 循环注册：配置页面设置参数 → Beat 定时执行

---

## 阶段 3：多平台编排迁移

**文件：** register_three_platforms.py (232行) + run_full_flow.py (282行)
**迁移到：** services/worker/tasks.py 新增编排任务

### 做什么

| 编排 | 新任务 | 说明 |
|------|--------|------|
| 三平台并发 | `register_all_platforms` task | 接收一个 email → 并发/顺序调用 Claude + ChatGPT + Grok 的 Flow |
| 端到端流程 | `full_flow` task | Outlook 注册 → 拿到 email → 调 `register_all_platforms` |

### 前端集成

- 仪表盘新增「一键全流程」按钮
- 选择：注册数量、目标平台、代理模式

### 依赖

- 阶段 2A/2B/2C 的三个 Flow 必须全部完成
- 阶段 1A 的邮箱中间件
- 阶段 2D 的 outlook_reg_loop（可选，作为邮箱供给源）

---

## 迁移顺序总结

```
Week 1:  阶段 1A (邮箱中间件) + 阶段 1B (下游集成)
         → 基础设施就绪

Week 2:  阶段 2A (Claude 注册) + 阶段 2B (ChatGPT 注册)
         → 两大核心平台可用

Week 3:  阶段 2C (Grok 注册) + 阶段 2D (运维工具)
         → 全平台 + 运维能力

Week 4:  阶段 3 (编排层)
         → 一键全流程
```

## 工作量估算

| 阶段 | 包装代码量 | 涉及旧脚本行数 | 新增测试 |
|------|----------|--------------|---------|
| 1A 邮箱中间件 | ~200 行 | 778 行 | ~8 个 |
| 1B 下游集成 | ~300 行 | 1033 行 | ~10 个 |
| 2A Claude 注册 | ~150 行 | 4041 行（实际包装 ~800） | ~4 个 |
| 2B ChatGPT 注册 | ~150 行 | 787 行 | ~4 个 |
| 2C Grok 注册 | ~150 行 | 859 行 | ~4 个 |
| 2D 运维工具 | ~200 行 | 1276 行 | ~6 个 |
| 3 编排层 | ~150 行 | 514 行 | ~4 个 |
| **总计** | **~1300 行新代码** | **9288 行旧代码** | **~40 个测试** |

## 不迁移的文件

以下文件保持原样，不进入新架构：

| 文件 | 行数 | 原因 |
|------|------|------|
| _botguard_extract.py | 127 | 调试工具 |
| _botguard_locate.py | 104 | 调试工具 |
| _capture_google_signup.py | 110 | 抓包工具 |
| _clash_verge.py | 885 | Clash 管理（大部分功能已在 proxy_manager 中） |
| _extract_bg_challenge.py | 122 | 调试工具 |
| _frida_inject.py | 43 | Frida 注入 |
| _inspect_phone.py | 90 | DOM 检查 |
| _inspect_steps.py | 153 | DOM 检查 |
| _login_with_cookies.py | 80 | 调试工具 |
| _test_gmail_web.py | 300 | 测试脚本 |
| _verify_login.py | 131 | 调试工具 |
| _walk_phone.py | 100 | 调试工具 |
| gmail_botguard_probe.py | 236 | BotGuard 研究 |
| register_gmail_protocol.py | 829 | 用户明确跳过 |
