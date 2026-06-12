# 功能扫描（feature_sweep）设计

- 日期：2026-06-12
- 目标：对**运行中的 services 栈**做一遍功能扫描——打每个 live 端点 + 触发每个 Celery 任务，逐功能报 通过/失败/gated。
- 用户选择：扫描形式（非测试套件）；副作用边界=**全打**（含真实创建/删除/触发注册）。

## 1. 覆盖面

| 目标 | 数量 | 方式 |
|---|---|---|
| gateway :8000 路由 | 25 路径 | HTTP |
| sms_service :8001 端点 | ~9 | HTTP |
| account_service :8002 端点 | ~12 | HTTP |
| config_service :8003 端点 | ~7 | HTTP |
| worker Celery 任务 | 12 | celery send_task + 轮询 |
| 注册流程 | register_outlook_single 触发到 ixBrowser/IP gate | celery |

## 2. 结构（单脚本 `services/scripts/feature_sweep.py`）

```
class SweepResult:  组, 功能, 方法, 目标, 状态, 判定(PASS/FAIL/ERROR/GATED), 备注, 耗时ms
class Sweep:        run(label, fn) 包 try/except 记录;  results 列表;  report()
功能组函数(每组自包含 建→查→改→删→清理):
  sweep_health        各服务 /health
  sweep_auth          login / users CRUD / api-keys CRUD
  sweep_config        config_service 端点(get/set/list)
  sweep_sms           sms_service 端点(balance/number 生命周期——外部调用如实记录)
  sweep_accounts      account CRUD(create→get→update→list→export→delete)
  sweep_proxy         gateway /proxy CRUD + test + status
  sweep_observability /dashboard /audit /logs
  sweep_alerts        /alerts/rules CRUD
  sweep_forwarding    gateway 转发 /accounts /sms /config(验证转发链路)
  sweep_tasks         12 任务逐个 send_task + 轮询 AsyncResult(收到/成功/失败)
  sweep_registration  register_outlook_single 触发,轮询片刻,报是否走到 ixBrowser/IP gate
```

## 3. 数据流 / 容错 / 清理

- 每个用例经 `Sweep.run()`：try 调用 → 记录状态码/判定/备注；except → 记 ERROR（**绝不中断整体扫描**）。
- 连接拒绝 → 该服务 DOWN（记录，继续）。
- Mutation 用例：create 拿 id → 用于 get/update → 末尾 delete 清理（best-effort），扫描可反复跑。
- 任务：`celery_app.send_task(name)` → `AsyncResult.get(timeout=N)` 或轮询 state；超时记 GATED/TIMEOUT。
- 注册：触发后轮询 worker 结果/日志，预期失败在浏览器/代理处 → 判定 GATED（基础设施通、卡外部门槛），不算 FAIL。

## 4. 报告

- 控制台：按组分节，每行 `判定 组/功能 方法 目标 → 状态 (备注)`；末尾汇总 `PASS=x FAIL=y ERROR=z GATED=w`。
- 存 `services/scripts/_sweep_report.json`（gitignore）。
- 退出码：有 FAIL/ERROR(非 GATED) → 非零（便于 CI/复跑判断）。

## 5. 配置

- 目标 URL 默认 `http://127.0.0.1:{8000,8001,8002,8003}`，可 env 覆盖。
- `REDIS_URL` 默认 `redis://127.0.0.1:6379/0`。

## 6. 非目标（YAGNI）

- 不做断言级别的深度校验（扫描 = 端点可达+合理响应+任务能执行；深度行为校验归集成测试套件，本次不做）。
- 不 mock 外部（用户选全打，真实调用如实记录成本/结果）。
- 不测注册的真实出号（需干净 IP；只验到 gate）。
- 不改 services 业务代码（纯外部扫描）。
