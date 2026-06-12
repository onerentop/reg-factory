# RegFactory services 运行指南

## 架构（容器 vs 宿主机）

```
┌─────────────────── Docker compose（可容器化）───────────────────┐
│  redis  ·  gateway:8000  ·  sms:8001  ·  account:8002  ·  config:8003 │
│  (DB-per-service，各自 SQLite 持久卷；服务间 HTTP 通信)               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Celery broker = redis
┌──────────────────────────┴──────────────────────────────────────┐
│  worker（宿主机 Windows，不进容器）                                  │
│  Celery worker + ixBrowser 桌面应用 + 根注册脚本(register_outlook…)   │
│  → 真正执行浏览器注册；需干净/移动 IP                                  │
└──────────────────────────────────────────────────────────────────┘
```

**为什么 worker 不在容器里**：ixBrowser 是 Windows 桌面浏览器自动化工具，无法进 Linux 容器；且 worker 经 `legacy_bridge` 依赖项目根目录的注册脚本。故 worker 在宿主机跑，连接 compose 起的 redis。

## 启动微服务（Docker）

```powershell
cd F:\reg-factory\services
docker compose up -d --build
```

健康检查：
```powershell
curl http://localhost:8000/health   # gateway
curl http://localhost:8002/health   # account（若实现 /health）
```

停止：`docker compose down`（加 `-v` 连数据卷一起删）。

## 启动 worker（宿主机）

worker 需要 ixBrowser 在跑 + 根脚本可用 + 代理。在项目根目录：
```powershell
cd F:\reg-factory\services
$env:REDIS_URL = "redis://localhost:6379/0"     # 指向 compose 的 redis
# 让 worker 能 import 根脚本（legacy_bridge 会把根加入 sys.path）
celery -A worker.tasks worker --loglevel=info --pool=solo    # Windows 用 solo 池
```
> 注册任务（`register_outlook_single` 等）经 gateway 触发 → 入 redis 队列 → worker 消费 → 调 flows（当前 LegacyBridgeStep → 根 register_outlook）。**注册成功仍需干净/移动 IP**（同根 loop）。

## 现状与限制（诚实交代）

- ✅ 4 个 FastAPI 微服务 + redis 可经 compose 起、彼此 HTTP 通。
- ⚠️ **worker 的注册链路端到端未验证**：worker 仍桥接根脚本（里程碑2b 原生化待干净 IP），且 ixBrowser + 干净 IP 是硬前置。
- ⚠️ **现在稳定出号的是根 `outlook_reg_loop.py`**（不经 services）。services 是在建的新系统，注册路径尚未实跑验证。
- DB 为 dev SQLite（DB-per-service）；生产建议换 postgres（设 `DATABASE_URL=postgresql+asyncpg://…`，需装 asyncpg）。

## 与根 loop 的关系

- **要量产账号（现在）**：直接跑根 `python outlook_reg_loop.py`（已验证）。
- **要走 services 新系统**：起 compose + 宿主机 worker；但注册端到端验证 = 里程碑2b Task 6（gated 待干净 IP）。
