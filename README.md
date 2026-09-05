# RegFactory

本机 **Outlook / Google 注册控制台**。项目将浏览器注册、代理、接码、账户结果和任务事件收敛在单机 FastAPI + React 控制台中。

> 仅支持 Outlook 与 Google。Claude、ChatGPT、Grok、Codex、Plus 激活、第三方 token 上传、多平台编排、告警、审计和定时任务均已移除。

## 功能

- **Outlook**：browser、hybrid、protocol 三种现有模式；成功账号统一保存到 SQLite；可在账户页提取 Graph refresh token。
- **Google 网页注册**：Donut/Playwright 保持同一浏览器会话直到手机验证；通过 SMS 服务配置取号、收码与释放。
- **Google Android 注册**：`gmail_android/` 的 BlueStacks + Appium 独立路径；默认在手机或安全验证步骤停下，需操作者处理后继续。
- **代理管理**：代理 CRUD、可用性检测、状态切换；注册 UI 只上传 `proxy_id`，认证串只在服务端组装。
- **本机任务控制**：有界 Windows 子进程、SQLite Job/事件持久化、任务日志 WebSocket 回放、应用重启后的安全中断标记。
- **浏览器 provider**：默认 Ant Browser（本地 API 19876），可切 ixBrowser / donut。

## 结构

```text
services/                 FastAPI 单体、SQLite、SMS、任务调度
frontend/                 React + Vite 控制台
common/                   Outlook / Google 共用浏览器、代理、接码工具
register_outlook_standalone.py
register_gmail_hybrid.py
register_gmail_protocol.py
gmail_android/            独立 BlueStacks/Appium Google 流程
```

## 前置条件

- Windows 10/11、Python 3.11+（services）与 Node.js。
- Ant Browser 正在运行，设置页已启用启动 API 服务（默认端口 19876）；或自行设 `BROWSER_PROVIDER=ixbrowser`/`donut`。
- Outlook/Google 实际注册按需要配置代理与接码凭据。
- 复制 `.env.example` 为 `.env`，仅填写需要的项；不要提交 `.env`。

## 安装与启动

```powershell
cd F:\reg-factory\services
python -m pip install -e .[dev]

cd ..\frontend
npm ci

cd ..
.\scripts\start_all.ps1
```

完成后打开 `http://127.0.0.1:8000`。开发前端可运行：

```powershell
npm --prefix frontend run dev
```

Vite 在 `3000` 启动并将 `/api`、`/ws` 代理至 `8000`。

## 使用顺序

1. 登录本机控制台。
2. 在 **代理** 页录入并测试代理。
3. 在 **接码平台** 页配置 provider；Google 网页注册还需填写 `gmail_sms_config`。
4. 在 **Outlook** 或 **Google** 页选择数量、代理后启动注册。
5. 在启动窗口内查看持久化 task log 与终态结果；成功账号出现在对应账户列表。
6. Outlook 成功账号需要 token 时，在账户行点击“提取 Token”。

## Google Android

Android 路径独立于网页/Donut 流程：

```powershell
cd F:\reg-factory\gmail_android
powershell -ExecutionPolicy Bypass -File .\scripts\run_gmail_register.ps1
```

它默认停止在手机/安全验证。完成人工验证后，按 `gmail_android/README.md` 使用 `--resume-after-phone`；只有在明确同意 Google Privacy and Terms 时才使用 `--accept-terms`。

## 验证

日常代码改动优先运行局部测试，不默认触发真实注册：

```powershell
cd F:\reg-factory\services
python -m pytest tests/gateway/test_registration_routes.py tests/worker/test_outlook_flow.py tests/worker/test_gmail_flow.py -q

cd ..\frontend
npm run test -- src/pages/AccountsPage.test.tsx
```

真实注册、浏览器 profile 创建、代理连通测试、验证码和手机取号都会产生第三方副作用，必须单独确认后执行。

详见 [services/SERVICES_RUN.md](services/SERVICES_RUN.md)。
