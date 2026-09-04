# RegFactory Outlook / Google 本机控制台

## 运行架构

```text
浏览器
  └─ http://127.0.0.1:8000
       ├─ FastAPI API / WebSocket
       ├─ frontend/dist 静态页面与 SPA 深链回退
       ├─ SQLite：services/data/regfactory.db
       └─ LocalProcessTaskManager（默认最多 1 个浏览器子进程）
```

运行时不需要 Docker、Redis、Celery、PostgreSQL 或 Nginx。浏览器注册使用根目录自动化依赖；`BROWSER_PROVIDER=donut` 是默认值，ixBrowser 仅作为本机回退兼容。

## 安装与启动

```powershell
cd F:\reg-factory\services
python -m pip install -e .[dev]

cd ..\frontend
npm ci

cd ..
.\scripts\start_all.ps1
```

启动脚本会构建前端、执行当前 SQLite migration，再以单 worker 启动：

```powershell
cd F:\reg-factory\services
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

**必须保持 `--workers 1`**：任务 IPC 队列和 task-log WebSocket 由同一个 API 进程持有。开发时可另开终端运行 `npm --prefix frontend run dev`，Vite 会代理 `/api` 与 `/ws`。

## 支持范围

- Outlook：browser / hybrid / protocol 模式注册、账号结果和可选 Graph refresh token 提取。
- Google：网页/Donut hybrid 注册；接码配置来自 SMS 服务与 `gmail_sms_config`。
- Google Android：`gmail_android/` 是独立 BlueStacks/Appium 流程，默认停在手机/安全验证处，操作者处理后可按其 README 继续。
- 代理：在控制台中新增、启停和连通性检查；注册请求只提交 `proxy_id`，服务端拼接认证连接串。

## 任务语义

- `POST /register/outlook` 和 `POST /register/google` 先持久化 `queued` Job，再投递受控子进程。
- `GET /tasks/{task_id}`、`GET /tasks/{task_id}/events` 与 `/ws/task/{task_id}/logs` 读取 SQLite 的任务投影和事件。
- API 重启会将未完成 Job 标记为 `interrupted`，绝不自动重放外部注册。
- 子进程不直接写 SQLite；API 父进程统一保存任务状态和成功账号。

## 验证原则

优先运行相关 worker、gateway、proxy、SMS、前端组件测试与 import smoke。不要默认运行真实注册、代理轮换、手机取号、验证码、浏览器 profile 创建或全量 E2E；这些会产生外部副作用，必须单独授权。
