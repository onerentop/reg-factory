# 后端 HTTP 路由行为测试 设计（阶段2）

- 日期：2026-06-12
- 缺口：后端 168 测试全是 repository/service 单元层，**0 个 TestClient**——HTTP 路由的请求→响应行为（校验/鉴权/handler）未覆盖。worker flows 已有 17 测试，不动。
- 范围：gateway 8 router(25 路由) + account/config/sms 自有路由(~28)。

## 1. 方式：FastAPI TestClient（进程内，无 Docker）

- `client = TestClient(app)`（**不加 `with`** → 不触发 lifespan → 无 create_all/seed/config_client 网络调用；路由用下面的 override，不碰真 DB）。
- `app.dependency_overrides[<dep>] = lambda: <fake>` 把服务依赖换 fake：`get_auth_service`/`get_audit_service`/`get_alert_engine`/`get_session` 等，返回 canned 数据。
- 测后 `app.dependency_overrides.clear()`（fixture teardown）。

## 2. 鉴权（gateway 保护端点）

`role_checker = RoleChecker(jwt_strategy)`，`Depends(role_checker.require_role("admin"))` 强制。
- **401**：不带 `Authorization` → 断言 401。
- **403**：带 readonly 角色 token → 断言 403。
- **happy**：`jwt_strategy` 签一个 admin token（fixture `admin_token`），`headers={"Authorization": f"Bearer {token}"}` → 过鉴权，断言 200 + 响应 shape。

## 3. 结构

```
tests/gateway/conftest.py        : client fixture(TestClient+overrides) + admin_token/readonly_token fixture + fake 服务
tests/gateway/test_auth_routes.py        : /auth/login /users /api-keys (含 401/403/happy)
tests/gateway/test_proxy_routes.py       : /proxy CRUD + test + status
tests/gateway/test_alerts_routes.py      : /alerts/rules
tests/gateway/test_observability_routes.py: /dashboard /audit /logs
tests/gateway/test_tools_routes.py       : /tools/* (mock celery send_task)
tests/gateway/test_orchestrate_routes.py : /orchestrate/*
tests/gateway/test_registration_routes.py: /register/outlook /tasks/{id} (mock celery)
tests/gateway/test_forwarding_routes.py  : /accounts /sms /config 转发(mock httpx 上游)
tests/<svc>/conftest.py + test_<svc>_routes.py : account/config/sms 自有路由
```

## 4. 每路由测什么（行为层，不重复 service 单元）

- **happy path**：合法请求 → 200 + 响应结构正确（mock service 返回 canned，断言路由正确组装/透传）。
- **校验**：缺必填/类型错 → 422。
- **鉴权**（保护端点）：401/403。
- **转发路由**：mock 上游 httpx → 断言 gateway 正确转发 method/path/body + 透传响应/错误。
- **任务路由**：mock `celery_app.send_task` → 断言用正确 task name/args 入队 + 返回 task id。

## 5. fake 服务策略

- `FakeAuthService`：`login` 返回带 token 的 LoginResponse / None；`create_user`/`list_users`/`create_api_key`/... 返回 canned。
- `get_session` override 成一个不被真用的占位（service 已 fake，session 不触达）。
- celery/httpx：`vi`等价用 `unittest.mock.patch` 或 monkeypatch。
- 各 fake 实现路由实际调用的方法签名（读 router 源确定）。

## 6. 验证 / 非目标

- `cd services && python -m pytest tests/ -q` 全绿（与现有 168 并存、不退）。
- 无需 Docker/redis/网络（全 mock/override）。
- 非目标：不测 service/repository 内部逻辑（已覆盖）；不做真 DB 集成（单独阶段）；websocket 深测（已有 test_websocket_hub）。
