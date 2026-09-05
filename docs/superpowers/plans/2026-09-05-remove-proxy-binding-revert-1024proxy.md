# 移除代理每日绑定、改回 1024proxy sid 轮换 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 Phase A 的 ProxyBinding「每 IP 每天一窗」绑定机制，恢复「注册从代理池取 1024proxy、每窗口轮换 sid 拿不同住宅出口 IP」的原始模型；代理池管理保留，Webshare 数据清空。

**Architecture:** 后端删除 `ProxyBindingService`/`ProxyBinding` 模型/绑定端点/worker 绑定生命周期/flows 的 `emit("binding")`；`registration.py` 恢复 `_resolve_proxy`+`_pick_active_proxy`，并在派发时对每个窗口 `rotate_proxy_sid`（经 `worker.tasks._helpers` 导入，该模块自举项目根路径）。新增 Alembic 迁移删表。前端去掉绑定/配额 UI 与「手动选代理强制 count=1」限制。

**Tech Stack:** FastAPI（services 单体，Python 3.11，`services/.venv`）、SQLAlchemy async、Alembic、pytest；前端 Vite/React/Antd、vitest。

**运行约定：** 后端命令在 `services/` 目录、用 `services/.venv/Scripts/python.exe`（裸 `python` 会解析到错误全局 venv）。前端命令在 `frontend/` 目录、用 `npm`。每个 Task 结束务必提交（commit message 附标准 `Co-Authored-By: Claude Opus 4.8` 与 `Claude-Session` 尾）。

---

### Task 1: 准备——固化未提交的 ixBrowser 改动 + 建特性分支

**背景：** 工作区有一套已完成、22 单测通过但**未提交**的 ixBrowser 代理注入改动（`common/ixbrowser_provider.py`、`common/browser.py`、`register_outlook_standalone.py`、`tests/test_ixbrowser_provider.py`）。本计划不碰它们，先固化。`.env` gitignored 不进提交。`services/.claude-flow/policy/state.json` 的改动**不要动**。

- [ ] **Step 1:** `cd /f/reg-factory && git status --short`（确认那 4 文件为 M/??）
- [ ] **Step 2:** `git add common/ixbrowser_provider.py common/browser.py register_outlook_standalone.py tests/test_ixbrowser_provider.py`
- [ ] **Step 3:** 提交，message: `feat(ixbrowser): 直连档+--proxy-server 注入+CDP 代理认证，绕过 ixBrowser 代理检测`
- [ ] **Step 4:** `git checkout -b feat/remove-proxy-binding`（确认 `git branch --show-current`）

---

### Task 2: 恢复 registration.py 的 sid 轮换（删 claim 路径）

**Files:** Modify `services/gateway/routers/registration.py`；Test `services/tests/gateway/test_registration_routes.py`

**说明：** `_resolve_proxy` 单次解析基础代理串（`proxy_id` > 显式 `proxy` > `_pick_active_proxy` 随机取活跃池条目），再对 `count` 个窗口分别 `rotate_proxy_sid` → 每窗不同出口 IP。`rotate_proxy_sid` 从 `worker.tasks._helpers` 导入（该模块自举项目根路径，使 gateway 可用 `common.proxy`）。

- [ ] **Step 1: 写失败测试** — 删 `test_register_multiple_tasks_use_distinct_proxies`，新增：

```python
def test_register_outlook_rotates_sid_per_window(client):
    """改回 1024proxy：count=2 每窗轮换 sid → 不同出口 IP，上游 host 不变。"""
    import re
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    base = "socks5://sb7f3017-region-Rand-sid-ORIG1234-t-5:pw@us.1024proxy.io:3000"
    response = client.post("/register/outlook", json={"count": 2, "proxy": base})
    assert response.status_code == 200
    used = [call[1]["proxy"] for call in runtime.submissions]
    assert len(used) == 2
    sids = [re.search(r"-sid-([A-Za-z0-9]+)-t-", p).group(1) for p in used]
    assert sids[0] != sids[1]
    assert all("us.1024proxy.io:3000" in p for p in used)
    assert all(p.startswith("socks5://sb7f3017-region-Rand-sid-") for p in used)
    assert base not in used
```

- [ ] **Step 2: 跑确认失败** — `cd /f/reg-factory/services && ../services/.venv/Scripts/python.exe -m pytest tests/gateway/test_registration_routes.py::test_register_outlook_rotates_sid_per_window -q`（FAIL）
- [ ] **Step 3: 重写 registration.py**（顶部到 `trigger_registration` 结束；`get_task_status`/`get_task_events` 不动）：

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.deps import get_session
from gateway.schemas import RegistrationRequest
from shared.base_schema import ApiResponse

router = APIRouter()
SUPPORTED_PLATFORMS = frozenset({"outlook", "google"})
SUPPORTED_MODES = {
    "outlook": frozenset({"browser", "hybrid", "protocol"}),
    "google": frozenset({"browser"}),
}


def _proxy_url(proxy) -> str:
    """仅在服务端将代理记录组装为连接串，密码绝不返回浏览器。"""
    auth = f"{proxy.username}:{proxy.password}@" if proxy.username and proxy.password else ""
    return f"{proxy.type or 'socks5'}://{auth}{proxy.host}:{proxy.port}"


async def _pick_active_proxy(session: AsyncSession) -> str:
    """从代理池取一个可用代理（active/available/slow）。"""
    import random
    from sqlalchemy import select
    from gateway.models import ProxyEntry
    result = await session.execute(select(ProxyEntry))
    available = [p for p in result.scalars().all() if p.status in ("active", "available", "slow")]
    return _proxy_url(random.choice(available)) if available else ""


async def _resolve_proxy(session: AsyncSession, proxy_id: str | None, proxy: str) -> str:
    """proxy_id 优先，其次显式 proxy 串，最后从池随机取活跃代理。"""
    if proxy_id:
        import uuid
        from sqlalchemy import select
        from gateway.models import ProxyEntry
        try:
            identifier = uuid.UUID(proxy_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid proxy_id") from error
        result = await session.execute(select(ProxyEntry).where(ProxyEntry.id == identifier))
        selected = result.scalar_one_or_none()
        if selected is None:
            raise HTTPException(status_code=404, detail="Proxy not found")
        return _proxy_url(selected)
    return proxy or (await _pick_active_proxy(session) if session is not None else "")


@router.post("/register/{platform}", response_model=ApiResponse)
async def trigger_registration(
    platform: str,
    body: RegistrationRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """先持久化任务，再交给本机有界子进程池执行；每窗口轮换 1024proxy sid。"""
    from gateway.registration_helpers import resolve_registration_mode
    from gateway.registration_jobs import RegistrationJobService
    from worker.tasks._helpers import rotate_proxy_sid  # 自举项目根路径后再引 common.proxy
    import uuid

    runtime = getattr(request.app.state, "task_manager", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="本机任务管理器尚未启动")
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=422, detail="Unsupported platform; use outlook or google")

    payload = body.model_dump()
    config = dict(body.config)
    mode = resolve_registration_mode(payload)
    if mode not in SUPPORTED_MODES[platform]:
        raise HTTPException(status_code=422, detail=f"Unsupported {platform} registration mode: {mode}")
    config["mode"] = mode

    if platform == "google":
        try:
            from config_service.repository import ConfigRepository, ConfigVersionRepository
            from config_service.service import ConfigService
            config_service = ConfigService(ConfigRepository(session), ConfigVersionRepository(session))
            entry = await config_service.get("gmail_sms_config")
            if entry is not None and isinstance(entry.value, dict):
                config["sms"] = entry.value
        except Exception as error:
            import logging
            logging.getLogger(__name__).warning("gmail_sms_config 拉取失败，跳过接码配置注入: %s", error)

    base_proxy = await _resolve_proxy(session, body.proxy_id, body.proxy)
    job_service = RegistrationJobService(session)
    task_ids: list[str] = []
    for index in range(body.count):
        task_id = str(uuid.uuid4())
        await job_service.enqueue(task_id, platform)
        if session is not None:
            await session.commit()
        await runtime.submit_registration(
            task_id, platform=platform, idx=index,
            proxy=rotate_proxy_sid(base_proxy),  # 每窗口不同 sid → 不同出口 IP
            config=config,
        )
        task_ids.append(task_id)
    return ApiResponse(data={"task_ids": task_ids, "status": "queued", "count": body.count})
```

- [ ] **Step 4: 修其余绑定测试** — `test_register_outlook_queues_local_task` 改为 body 传 `"proxy": "socks5://1.2.3.4:1080"`（不再 patch claim），断言 `"1.2.3.4:1080" in call["proxy"]`；`test_register_uses_proxy_id_without_exposing_password` 改为经 `app.dependency_overrides[get_session]` 注入一个假 `_Session`（其 `execute()` 返回带 `scalar_one_or_none()->ProxyEntry(...,password="s3cr3t-pw",host="9.9.9.9",port=1080)` 的结果、`commit()` 空实现），断言响应体不含密码、`call["proxy"]` 含密码与 `9.9.9.9:1080`。删除文件内 `_claim`/`ProxyClaim`/`ProxyBindingService` 引用。
- [ ] **Step 5: 跑通** — `../services/.venv/Scripts/python.exe -m pytest tests/gateway/test_registration_routes.py -q`（PASS）
- [ ] **Step 6: 提交** — `git add services/gateway/routers/registration.py services/tests/gateway/test_registration_routes.py`，message `feat(register): 删 claim 路径，恢复每窗口轮换 1024proxy sid`

---

### Task 3: 移除 worker 绑定生命周期与 flows 的 emit("binding")

**Files:** `services/worker/local_task_manager.py`、`services/worker/flows/outlook.py`、`services/worker/flows/gmail.py`

- [ ] **Step 1: 删 local_task_manager.py** — 两处 `await self._release_binding(...)`（原 145、155）；5 处 `await self._finalize_binding(task_id, ...)`（原 314、326、337、355、402）；`elif event_type == "binding":` 整段（原 338–342）；三个方法 `_persist_binding`/`_finalize_binding`/`_release_binding`（原 407–433）。
- [ ] **Step 2: 删 flows/outlook.py** — 去掉 `_on_window` 定义与传参，browser 分支改为 `result = await _register_one_browser(bb, idx, proxy_str)`。
- [ ] **Step 3: 删 flows/gmail.py** — 删原 49–52 行（两行注释 + `if services is not None: services.emit("binding", {...})`）。
- [ ] **Step 4: 语法自检** — `cd /f/reg-factory/services && ../services/.venv/Scripts/python.exe -c "import ast; [ast.parse(open(f,encoding='utf-8').read()) for f in ['worker/local_task_manager.py','worker/flows/outlook.py','worker/flows/gmail.py']]; print('OK')"`
- [ ] **Step 5: 跑 worker 测试** — `../services/.venv/Scripts/python.exe -m pytest tests/worker -q`（PASS 或 no tests）
- [ ] **Step 6: 提交** — message `refactor(worker): 移除代理绑定生命周期与 flows 的 binding 上报`

---

### Task 4: 移除 proxy 路由绑定端点与列表绑定字段

**Files:** `services/gateway/routers/proxy.py`、`services/tests/gateway/test_proxy_routes.py`

- [ ] **Step 1: 精简 `list_proxies`**：

```python
@router.get("/proxy", response_model=ApiResponse)
async def list_proxies(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(select(ProxyEntry).order_by(ProxyEntry.created_at.desc()))
    proxies = result.scalars().all()
    return ApiResponse(data=[{
        "id": str(p.id), "type": p.type, "host": p.host, "port": p.port,
        "username": p.username, "has_password": bool(p.password), "status": p.status,
        "region": p.region,
    } for p in proxies])
```

- [ ] **Step 2:** 删 `/proxy/quota` 与 `/proxy/{proxy_id}/bindings`（原 146–171 整块）。
- [ ] **Step 3:** 删 test_proxy_routes.py 里 quota/bindings 测试与绑定字段断言，补：

```python
def test_list_proxies_has_no_binding_fields(client):
    resp = client.get("/proxy")
    assert resp.status_code == 200
    for row in resp.json()["data"]:
        assert "today_bound" not in row
        assert "available_today" not in row
        assert {"id", "host", "port", "status"} <= set(row)
```

- [ ] **Step 4:** `cd /f/reg-factory/services && ../services/.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_routes.py -q`（PASS）
- [ ] **Step 5: 提交** — message `refactor(proxy): 删配额/绑定明细端点与列表绑定字段`

---

### Task 5: 删除 ProxyBindingService、ProxyBinding 模型及测试

**Files:** Delete `services/gateway/proxy_binding_service.py`、`services/tests/gateway/test_proxy_binding_service.py`；Modify `services/gateway/models.py`、`services/shared/database.py`

- [ ] **Step 1:** 确认无残留引用：`cd /f/reg-factory && grep -rn "ProxyBindingService\|ProxyBinding\|proxy_binding_service" services/gateway services/worker --include=*.py | grep -v "proxy_binding_service.py"`（应无输出）
- [ ] **Step 2:** `git rm services/gateway/proxy_binding_service.py services/tests/gateway/test_proxy_binding_service.py`
- [ ] **Step 3:** 删 models.py 的 `ProxyBinding` 类（原 82–102 整块），保留 `ProxyEntry`；未使用 import 保留即可。
- [ ] **Step 4:** 清理 database.py 注释（binding→中性表述如「SQLite 显式事务控制」），**不改** `isolation_level=None`+显式 BEGIN 实现。
- [ ] **Step 5:** `cd /f/reg-factory/services && ../services/.venv/Scripts/python.exe -c "import gateway.models, gateway.routers.proxy, gateway.routers.registration; print('imports OK')" && ../services/.venv/Scripts/python.exe -m pytest tests/shared/test_database_transactions.py -q`（若该测试原建 proxy_bindings 表，改用 proxy_entries 或普通事务复现同语义）
- [ ] **Step 6: 提交** — `git add -A`，message `refactor(gateway): 删除 ProxyBindingService 与 ProxyBinding 模型`

---

### Task 6: 新增 Alembic 迁移删除 proxy_bindings 表

**Files:** Create `services/migrations/versions/20260905_05_drop_proxy_bindings.py`（当前迁移头 `20260904_04`）

- [ ] **Step 1: 建迁移**：

```python
"""Drop per-day proxy_bindings table (revert to 1024proxy sid rotation).

Revision ID: 20260905_05
Revises: 20260904_04
Create Date: 2026-09-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260905_05"
down_revision: Union[str, Sequence[str], None] = "20260904_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_proxy_bindings_proxy_date", table_name="proxy_bindings")
    op.drop_index("ix_proxy_bindings_task_id", table_name="proxy_bindings")
    op.drop_index("ix_proxy_bindings_proxy_id", table_name="proxy_bindings")
    op.drop_table("proxy_bindings")


def downgrade() -> None:
    op.create_table(
        "proxy_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("proxy_id", sa.Uuid(), sa.ForeignKey("proxy_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bound_date", sa.Date(), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("profile_id", sa.String(32), nullable=True),
        sa.Column("profile_name", sa.String(255), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="claimed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("proxy_id", "bound_date", name="uq_proxy_bindings_proxy_date"),
    )
    op.create_index("ix_proxy_bindings_proxy_id", "proxy_bindings", ["proxy_id"])
    op.create_index("ix_proxy_bindings_task_id", "proxy_bindings", ["task_id"])
    op.create_index("ix_proxy_bindings_proxy_date", "proxy_bindings", ["proxy_id", "bound_date"])
```

- [ ] **Step 2:** `cd /f/reg-factory/services && ../services/.venv/Scripts/python.exe -m alembic upgrade head && ../services/.venv/Scripts/python.exe -m alembic current`（head=20260905_05）
- [ ] **Step 3:** 确认表删：`../services/.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('data/regfactory.db'); print(c.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='proxy_bindings'\").fetchall())"`（`[]`）
- [ ] **Step 4: 提交** — message `feat(db): 迁移删除 proxy_bindings 表`

---

### Task 7: 前端 ProxyPage 去掉绑定/配额 UI

**Files:** `frontend/src/pages/ProxyPage.tsx`、`frontend/src/pages/ProxyPage.test.tsx`

- [ ] **Step 1:** 删接口里 `today_bound`/`total_bound`/`today_profile_name`/`available_today`（原 16–19）。
- [ ] **Step 2:** 删 `const [bindings, setBindings] = useState(...)`（原 32）与 `loadBindings` 函数（原 104–110）。
- [ ] **Step 3:** 删「今日 / 累计」列（原 242–254 整个列对象）。
- [ ] **Step 4:** 表头改为仅 `已激活 {proxies.filter(p => p.active !== false).length} / {proxies.length}`（删「｜今日可用 ...」）。
- [ ] **Step 5:** 删 Table 的 `expandable={{ ... }}` 绑定明细（原 332–350+ 整块）。
- [ ] **Step 6:** 更新 ProxyPage.test.tsx（删绑定 mock/断言），补 `expect(screen.queryByText(/今日 \/ 累计/)).toBeNull()` 与 `expect(screen.queryByText(/今日可用/)).toBeNull()`。
- [ ] **Step 7:** `cd /f/reg-factory/frontend && npm run test -- src/pages/ProxyPage.test.tsx && npx tsc --noEmit`（PASS）
- [ ] **Step 8: 提交** — message `feat(frontend): 代理页移除绑定/配额 UI，回归普通池管理`

---

### Task 8: 前端 AccountsPage 解除「手动选代理强制 count=1」

**Files:** `frontend/src/pages/AccountsPage.tsx`、`frontend/src/pages/AccountsPage.test.tsx`

- [ ] **Step 1:** 原 152 行 `count: selectedProxyId ? 1 : registerCount,` → `count: registerCount,`；数量输入框（原 514–515 附近）`value={selectedProxyId ? 1 : registerCount}` + `disabled={!!selectedProxyId}` → `value={registerCount}`（删 disabled）；删「已选代理数量锁 1」提示（`{selectedProxyId && (...)}`）若有。
- [ ] **Step 2:** 保留 `selectedProxyId` 下拉与 `proxy_id: selectedProxyId || undefined`（原 153）。
- [ ] **Step 3:** 更新 AccountsPage.test.tsx（若断言「选代理后锁 1」，改为「仍可 count>1」）。
- [ ] **Step 4:** `cd /f/reg-factory/frontend && npm run test -- src/pages/AccountsPage.test.tsx && npx tsc --noEmit`（PASS）
- [ ] **Step 5: 提交** — message `feat(frontend): 解除手动选代理强制单窗限制`

---

### Task 9: 运行期数据清理（删 Webshare、启用 1024proxy）

**背景：** 本机运行期数据，不进 git；有外部副作用（改代理池），**执行前需用户授权**。需 API（8000）在跑。

- [ ] **Step 1:** `curl -s -m 4 http://127.0.0.1:8000/api/health`（status ok）
- [ ] **Step 2:** 删非 1024proxy 条目 — 只读查 `SELECT id FROM proxy_entries WHERE host != 'us.1024proxy.io'`（`services/data/regfactory.db`，`mode=ro`），逐个 `DELETE /api/proxy/{id}`。
- [ ] **Step 3:** 启用 1024proxy — 查 `host='us.1024proxy.io'` 的 id，`PUT /api/proxy/{id}/status` body `{"status":"active"}`（若池中无该条目，先在代理页加一条）。
- [ ] **Step 4:** 校验 `GET /api/proxy`：仅 `us.1024proxy.io`、含 `active`。

---

### Task 10: 全量回归

- [ ] **Step 1:** `cd /f/reg-factory/services && ../services/.venv/Scripts/python.exe -m pytest -q`（PASS，无 proxy_binding 失败）
- [ ] **Step 2:** `cd /f/reg-factory/frontend && npm run test && npm run build`（PASS）
- [ ] **Step 3:** 重启 API 后探 `/api/proxy/quota` 与 `/api/proxy/<uuid>/bindings` 均返回 404。
- [ ] **Step 4:** 交由 `superpowers:finishing-a-development-branch` 合并 `feat/remove-proxy-binding`。

---

## Self-Review

- **Spec 覆盖：** §2 删除清单 → Task 3/4/5；§3 恢复 sid 轮换 → Task 2；§4 迁移+数据+database.py → Task 6/9/Task5-Step4；§5 前端 → Task 7/8；§6 测试 → 各 Task 测试步 + Task 10；§7 范围外(ixBrowser 未提交) → Task 1。全覆盖。
- **占位符扫描：** 无 TBD/TODO；核心代码（registration、迁移、测试）给出完整代码，removal 步骤给出具体行段。
- **类型/命名一致：** `_resolve_proxy`/`_pick_active_proxy`/`_proxy_url` 同原始命名；`rotate_proxy_sid` 统一经 `worker.tasks._helpers` 导入；迁移 `revision=20260905_05 / down_revision=20260904_04` 与现有头衔接。
- **可运行性：** Task 2→3→4 先清空所有 `ProxyBindingService` 引用，Task 5 才删服务/模型，Task 6 才删表——每步之间应用可导入、可启动。
