# 代理池批量导入与「当天一 IP 一窗口」实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 100 条 Webshare 静态 IP 一次导入代理池，每个注册任务各自抢占一个当天未用过的 IP，代理列表能看到绑定的窗口与个数，且数据库层面保证当天一个 IP 只绑一个窗口。

**Architecture:** 新增 `proxy_bindings` 表，用 `UNIQUE(proxy_id, bound_date)` 做硬保证；`ProxyBindingService` 负责原子抢占（`begin_nested()` savepoint 隔离冲突重试）与状态回填；注册路由把代理解析从循环外挪进循环，每任务各抢一个；窗口 ID 由 worker 经既有事件流回传给父进程落库。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + SQLite + alembic；React 18 + antd 5 + Vitest；pytest。

**设计依据:** `docs/superpowers/specs/2026-09-04-proxy-daily-binding-design.md`

**运行环境提醒:** 本机 PATH 上的 `python` 指向 hermes-agent 全局 venv（无本项目依赖）。所有 Python 命令必须用 `services/.venv/Scripts/python.exe`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `services/gateway/proxy_import.py` | **新建** 代理文本解析，纯函数、无 DB/网络依赖 |
| `services/gateway/models.py` | **改** 增 `ProxyBinding` 模型 |
| `services/migrations/versions/20260904_04_proxy_bindings.py` | **新建** 建表迁移 |
| `services/gateway/proxy_manager.py` | **改** 增 `DailyUniqueAllocator`；`LeastUsedAllocator` 支持外部计数种子 |
| `services/gateway/proxy_binding_service.py` | **新建** 抢占/回填/聚合，唯一持有 binding 事务逻辑 |
| `services/gateway/routers/proxy.py` | **改** 增 import / bindings / quota 端点，列表加聚合字段 |
| `services/gateway/routers/registration.py` | **改** 每任务各抢一个代理 |
| `services/gateway/schemas.py` | **改** 增 `ProxyImportRequest` |
| `services/worker/flows/base.py` | **改** 增 `TaskEventEmitter` / `QueueEventEmitter`；`FlowRegistry.get` 接受 services |
| `services/worker/tasks/registration.py` | **改** 构造 emitter 注入 flow |
| `services/worker/flows/gmail.py` / `outlook.py` | **改** 建窗口后立刻 emit binding |
| `services/worker/local_task_manager.py` | **改** `_handle_event` 增 binding 分支与终态收尾 |
| `common/ixbrowser_provider.py` | **改** `_parse_proxy` 增 `default_type` 参数 |
| `frontend/src/pages/ProxyPage.tsx` | **改** 批量导入 Modal + 今日/累计列 + 展开明细 |
| `frontend/src/pages/AccountsPage.tsx` | **改** 已用代理禁选、锁数量、skipped 提示 |

---

### Task 1: 代理文本解析器

**Files:**
- Create: `services/gateway/proxy_import.py`
- Test: `services/tests/gateway/test_proxy_import.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/gateway/test_proxy_import.py
"""代理文本解析纯函数测试。无 DB、无网络。"""
from gateway.proxy_import import ProxyDraft, parse_proxy_lines


def test_webshare_four_field_format_uses_default_type():
    drafts, invalid = parse_proxy_lines("45.61.125.104:6115:proxyuser:proxypass", "http")
    assert invalid == []
    assert drafts == [ProxyDraft(type="http", host="45.61.125.104", port=6115,
                                 username="proxyuser", password="proxypass")]


def test_userpass_at_host_format():
    drafts, _ = parse_proxy_lines("u:p@1.2.3.4:8080", "http")
    assert drafts[0].username == "u" and drafts[0].password == "p"
    assert drafts[0].host == "1.2.3.4" and drafts[0].port == 8080


def test_host_port_only_has_no_credentials():
    drafts, _ = parse_proxy_lines("1.2.3.4:8080", "http")
    assert drafts[0].username is None and drafts[0].password is None


def test_scheme_prefix_overrides_default_type():
    drafts, _ = parse_proxy_lines("socks5://u:p@1.2.3.4:1080", "http")
    assert drafts[0].type == "socks5" and drafts[0].port == 1080


def test_blank_lines_and_comments_are_skipped():
    drafts, invalid = parse_proxy_lines("\n# comment\n\n1.2.3.4:8080\n", "http")
    assert len(drafts) == 1 and invalid == []


def test_garbage_line_is_reported_with_line_number():
    drafts, invalid = parse_proxy_lines("1.2.3.4:8080\ngarbage", "http")
    assert len(drafts) == 1
    assert invalid[0].line_no == 2 and invalid[0].raw == "garbage"


def test_non_numeric_port_is_invalid():
    _, invalid = parse_proxy_lines("1.2.3.4:notaport", "http")
    assert len(invalid) == 1


def test_out_of_range_port_is_invalid():
    _, invalid = parse_proxy_lines("1.2.3.4:70000", "http")
    assert len(invalid) == 1
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_import.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'gateway.proxy_import'`

- [ ] **Step 3: 写实现**

```python
# services/gateway/proxy_import.py
"""代理列表文本解析。纯函数，无 DB / 网络依赖，便于隔离测试。

支持格式（每行一条）：
    host:port:user:pass          Webshare 导出格式
    user:pass@host:port
    host:port
    以上均可带 socks5:// / http:// / https:// 前缀，前缀优先于 default_type
空行与 # 开头的注释行被跳过。
"""
from dataclasses import dataclass

_SCHEMES = ("socks5://", "https://", "http://")


@dataclass(frozen=True)
class ProxyDraft:
    type: str
    host: str
    port: int
    username: str | None
    password: str | None


@dataclass(frozen=True)
class InvalidLine:
    line_no: int
    raw: str
    reason: str


def _build(ptype: str, host: str, port: str, user: str | None, pwd: str | None) -> ProxyDraft | None:
    if not host or not port.isdigit():
        return None
    port_num = int(port)
    if not 1 <= port_num <= 65535:
        return None
    return ProxyDraft(type=ptype, host=host, port=port_num, username=user or None, password=pwd or None)


def _parse_one(line: str, ptype: str) -> ProxyDraft | None:
    if "@" in line:                       # user:pass@host:port
        cred, _, addr = line.rpartition("@")
        user, _, pwd = cred.partition(":")
        host, _, port = addr.rpartition(":")
        return _build(ptype, host, port, user, pwd)
    parts = line.split(":")
    if len(parts) == 4:                   # host:port:user:pass
        return _build(ptype, parts[0], parts[1], parts[2], parts[3])
    if len(parts) == 2:                   # host:port
        return _build(ptype, parts[0], parts[1], None, None)
    return None


def parse_proxy_lines(text: str, default_type: str = "http") -> tuple[list[ProxyDraft], list[InvalidLine]]:
    drafts: list[ProxyDraft] = []
    invalid: list[InvalidLine] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ptype = default_type
        for scheme in _SCHEMES:
            if line.lower().startswith(scheme):
                ptype = scheme[:-3]
                line = line[len(scheme):]
                break
        draft = _parse_one(line, ptype)
        if draft is None:
            invalid.append(InvalidLine(line_no=line_no, raw=raw, reason="无法识别的代理格式"))
        else:
            drafts.append(draft)
    return drafts, invalid
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_import.py -q
```
Expected: PASS，8 passed

- [ ] **Step 5: 提交**

```bash
git add services/gateway/proxy_import.py services/tests/gateway/test_proxy_import.py
git commit -m "feat(proxy): 代理列表文本解析器，支持 Webshare 四段式等四种格式"
```

---

### Task 2: ProxyBinding 模型与迁移

**Files:**
- Modify: `services/gateway/models.py:1-12`（导入）、末尾追加模型
- Create: `services/migrations/versions/20260904_04_proxy_bindings.py`

- [ ] **Step 1: 加模型**

`services/gateway/models.py` 第 1-12 行的 import 块，在 `Text,` 之后加 `Date,`：

```python
from sqlalchemy import (
    Column,
    String,
    JSON,
    Boolean,
    Integer,
    DateTime,
    Date,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
```

文件末尾追加：

```python
class ProxyBinding(TimestampMixin, BaseModel):
    """代理与 ixBrowser 窗口的当天绑定。

    UNIQUE(proxy_id, bound_date) 在数据库层保证「当天一个 IP 只绑一个窗口」，
    不依赖应用层的先查后插。bound_date 用本地自然日，与 TimestampMixin 的 UTC 时间戳不同。
    """
    __tablename__ = "proxy_bindings"
    __table_args__ = (
        UniqueConstraint("proxy_id", "bound_date", name="uq_proxy_bindings_proxy_date"),
        Index("ix_proxy_bindings_proxy_date", "proxy_id", "bound_date"),
    )

    proxy_id = Column(
        ForeignKey("proxy_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bound_date = Column(Date, nullable=False)
    task_id = Column(String(64), nullable=True, index=True)
    profile_id = Column(String(32), nullable=True)
    profile_name = Column(String(255), nullable=True)
    platform = Column(String(32), nullable=True)
    status = Column(String(20), nullable=False, default="claimed")
```

- [ ] **Step 2: 写迁移**

```python
# services/migrations/versions/20260904_04_proxy_bindings.py
"""Track per-day proxy-to-window bindings.

Revision ID: 20260904_04
Revises: 20260811_03
Create Date: 2026-09-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_04"
down_revision: Union[str, Sequence[str], None] = "20260811_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proxy_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "proxy_id",
            sa.Uuid(),
            sa.ForeignKey("proxy_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
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


def downgrade() -> None:
    op.drop_index("ix_proxy_bindings_proxy_date", table_name="proxy_bindings")
    op.drop_index("ix_proxy_bindings_task_id", table_name="proxy_bindings")
    op.drop_index("ix_proxy_bindings_proxy_id", table_name="proxy_bindings")
    op.drop_table("proxy_bindings")
```

- [ ] **Step 3: 跑迁移**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m alembic upgrade head
```
Expected: `Running upgrade 20260811_03 -> 20260904_04`

- [ ] **Step 4: 验证表结构与唯一约束**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -c "
import sqlite3; c = sqlite3.connect('data/regfactory.db')
print([r[1] for r in c.execute('PRAGMA table_info(proxy_bindings)')])
print([r[1] for r in c.execute('PRAGMA index_list(proxy_bindings)') if r[2]])
"
```
Expected: 列出 9 个字段；唯一索引里含 `uq_proxy_bindings_proxy_date`

- [ ] **Step 5: 提交**

```bash
git add services/gateway/models.py services/migrations/versions/20260904_04_proxy_bindings.py
git commit -m "feat(proxy): proxy_bindings 表，唯一约束保证当天一IP一窗口"
```

---

### Task 3: DailyUniqueAllocator

**Files:**
- Modify: `services/gateway/proxy_manager.py:42-53`（`LeastUsedAllocator`）、追加新类
- Test: `services/tests/gateway/test_proxy_allocator.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/gateway/test_proxy_allocator.py
"""代理分配策略测试。纯逻辑，无 DB。"""
from gateway.proxy_manager import DailyUniqueAllocator, LeastUsedAllocator, RandomAllocator


def test_excludes_proxies_bound_today():
    proxies = [{"id": "a"}, {"id": "b"}]
    picked = DailyUniqueAllocator(RandomAllocator(), {"a"}).select(proxies)
    assert picked["id"] == "b"


def test_returns_none_when_all_bound_today():
    proxies = [{"id": "a"}, {"id": "b"}]
    assert DailyUniqueAllocator(RandomAllocator(), {"a", "b"}).select(proxies) is None


def test_returns_none_on_empty_pool():
    assert DailyUniqueAllocator(RandomAllocator(), set()).select([]) is None


def test_delegates_ordering_to_inner_allocator():
    """内层 LeastUsed 用外部计数种子，选累计最少的那个。"""
    proxies = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    inner = LeastUsedAllocator({"a": 5, "b": 1, "c": 9})
    assert DailyUniqueAllocator(inner, set()).select(proxies)["id"] == "b"


def test_least_used_seed_is_optional():
    """不传种子时保持原有行为，全部计 0，返回第一个。"""
    assert LeastUsedAllocator().select([{"id": "a"}, {"id": "b"}])["id"] == "a"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_allocator.py -q
```
Expected: FAIL — `ImportError: cannot import name 'DailyUniqueAllocator'`

- [ ] **Step 3: 改 `LeastUsedAllocator` 接受计数种子**

把 `services/gateway/proxy_manager.py:42-53` 整段替换为：

```python
class LeastUsedAllocator(ProxyAllocator):
    """最少使用优先。usage 可传入外部计数（如 DB 里的累计绑定数）作为初始种子。"""

    def __init__(self, usage: dict[str, int] | None = None):
        self._usage: dict[str, int] = defaultdict(int)
        if usage:
            self._usage.update(usage)

    def select(self, proxies: list[dict]) -> dict | None:
        if not proxies:
            return None
        proxy = min(proxies, key=lambda p: self._usage.get(p.get("id", ""), 0))
        self._usage[proxy.get("id", "")] += 1
        return proxy
```

- [ ] **Step 4: 追加 `DailyUniqueAllocator`**

在 `ALLOCATOR_MAP` 定义之前插入：

```python
class DailyUniqueAllocator(ProxyAllocator):
    """装饰器：先滤掉当天已绑定的代理，再委托内层策略挑选。

    与 DB 无关——调用方负责把「今日已绑定的 proxy id 集合」查出来传进来，
    本类只做过滤与委托，可纯单测。
    """

    def __init__(self, inner: ProxyAllocator, bound_today: set[str]):
        self._inner = inner
        self._bound = bound_today

    def select(self, proxies: list[dict]) -> dict | None:
        return self._inner.select([p for p in proxies if str(p.get("id", "")) not in self._bound])
```

- [ ] **Step 5: 跑测试确认通过（含既有测试不回归）**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_allocator.py tests/worker/test_proxy_helpers.py -q
```
Expected: PASS，5 passed + 既有 proxy_helpers 全绿

- [ ] **Step 6: 提交**

```bash
git add services/gateway/proxy_manager.py services/tests/gateway/test_proxy_allocator.py
git commit -m "feat(proxy): DailyUniqueAllocator 过滤当天已绑定，LeastUsed 支持计数种子"
```

---

### Task 4: ProxyBindingService

**Files:**
- Create: `services/gateway/proxy_binding_service.py`
- Test: `services/tests/gateway/test_proxy_binding_service.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/gateway/test_proxy_binding_service.py
"""绑定抢占服务测试。用内存 SQLite 建真表，验证唯一约束真的拦得住。"""
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gateway.models import ProxyBinding, ProxyEntry
from gateway.proxy_binding_service import ProxyBindingService, build_proxy_url
from shared.base_model import BaseModel


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _add_proxy(session, host="1.2.3.4", status="active"):
    proxy = ProxyEntry(type="http", host=host, port=8080, username="u",
                       password="p", status=status)
    session.add(proxy)
    await session.flush()
    return proxy


@pytest.mark.asyncio
async def test_claim_returns_url_and_creates_binding(session):
    proxy = await _add_proxy(session)
    claim = await ProxyBindingService(session).claim("task-1", "google")
    assert claim is not None
    assert claim.proxy_url == "http://u:p@1.2.3.4:8080"
    assert claim.proxy_id == proxy.id


@pytest.mark.asyncio
async def test_second_claim_picks_a_different_proxy(session):
    await _add_proxy(session, host="1.1.1.1")
    await _add_proxy(session, host="2.2.2.2")
    svc = ProxyBindingService(session)
    first = await svc.claim("task-1", "google")
    second = await svc.claim("task-2", "google")
    assert first.proxy_id != second.proxy_id


@pytest.mark.asyncio
async def test_claim_returns_none_when_pool_exhausted_today(session):
    await _add_proxy(session)
    svc = ProxyBindingService(session)
    assert await svc.claim("task-1", "google") is not None
    assert await svc.claim("task-2", "google") is None


@pytest.mark.asyncio
async def test_inactive_proxies_are_not_candidates(session):
    await _add_proxy(session, status="inactive")
    assert await ProxyBindingService(session).claim("task-1", "google") is None


@pytest.mark.asyncio
async def test_yesterday_binding_does_not_block_today(session):
    proxy = await _add_proxy(session)
    session.add(ProxyBinding(proxy_id=proxy.id, bound_date=date.today() - timedelta(days=1),
                             task_id="old", status="success"))
    await session.flush()
    assert await ProxyBindingService(session).claim("task-1", "google") is not None


@pytest.mark.asyncio
async def test_claim_specific_conflicts_when_already_bound_today(session):
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    assert await svc.claim_specific(proxy.id, "task-1", "google") is not None
    assert await svc.claim_specific(proxy.id, "task-2", "google") is None


@pytest.mark.asyncio
async def test_session_still_usable_after_conflict(session):
    """撞唯一约束后事务必须仍可用——savepoint 隔离生效的证明。"""
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim_specific(proxy.id, "task-1", "google")
    await svc.claim_specific(proxy.id, "task-2", "google")
    await _add_proxy(session, host="9.9.9.9")      # 冲突后还能继续写
    await session.flush()


@pytest.mark.asyncio
async def test_mark_opened_then_finalize_keeps_binding(session):
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim("task-1", "google")
    await svc.mark_opened("task-1", "777", "a@gmail.com")
    await svc.finalize("task-1", success=True)
    summary = await svc.today_summary()
    assert summary[str(proxy.id)]["today_bound"] == 1
    assert summary[str(proxy.id)]["today_profile_name"] == "a@gmail.com"


@pytest.mark.asyncio
async def test_finalize_releases_binding_that_never_opened(session):
    """窗口没建成 → 删记录还回当天配额。"""
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim("task-1", "google")
    await svc.finalize("task-1", success=False)
    assert await svc.claim("task-2", "google") is not None


@pytest.mark.asyncio
async def test_finalize_keeps_opened_binding_on_failure(session):
    """窗口建成过就算占用，失败也不还。"""
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim("task-1", "google")
    await svc.mark_opened("task-1", "777", None)
    await svc.finalize("task-1", success=False)
    assert await svc.claim("task-2", "google") is None


@pytest.mark.asyncio
async def test_today_summary_counts_total_and_today(session):
    proxy = await _add_proxy(session)
    session.add(ProxyBinding(proxy_id=proxy.id, bound_date=date.today() - timedelta(days=2),
                             task_id="old", status="success"))
    await session.flush()
    await ProxyBindingService(session).claim("task-1", "google")
    summary = await ProxyBindingService(session).today_summary()
    assert summary[str(proxy.id)]["total_bound"] == 2
    assert summary[str(proxy.id)]["today_bound"] == 1


def test_build_proxy_url_without_credentials():
    proxy = ProxyEntry(type="http", host="1.2.3.4", port=8080, username=None, password=None)
    assert build_proxy_url(proxy) == "http://1.2.3.4:8080"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_binding_service.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'gateway.proxy_binding_service'`

若报 `pytest_asyncio` 缺失，先装：`./.venv/Scripts/python.exe -m pip install pytest-asyncio`，并确认 `services/pyproject.toml` 的 `[project.optional-dependencies].dev` 含 `pytest-asyncio>=0.23.0`，没有就加上。

- [ ] **Step 3: 写实现**

```python
# services/gateway/proxy_binding_service.py
"""代理当天绑定的抢占、回填与聚合。

唯一持有 proxy_bindings 事务逻辑的地方。抢占靠 UNIQUE(proxy_id, bound_date)
做硬保证，不用「先查后插」——并发下先查后插必然漏。
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models import ProxyBinding, ProxyEntry
from gateway.proxy_manager import DailyUniqueAllocator, LeastUsedAllocator

ACTIVE_STATUSES = ("active", "available")


def today_local() -> date:
    """本地自然日。注意 TimestampMixin 的时间戳是 UTC，两者不可混用。"""
    return datetime.now().date()


def build_proxy_url(proxy: ProxyEntry) -> str:
    """组装连接串。密码只在服务端出现，绝不返回浏览器。"""
    auth = f"{proxy.username}:{proxy.password}@" if proxy.username and proxy.password else ""
    return f"{proxy.type or 'socks5'}://{auth}{proxy.host}:{proxy.port}"


@dataclass(frozen=True)
class ProxyClaim:
    proxy_url: str
    binding_id: uuid.UUID
    proxy_id: uuid.UUID


class ProxyBindingService:
    def __init__(self, session: AsyncSession):
        self._session = session

    # ---------------- 查询 ----------------

    async def get_proxy(self, proxy_id) -> ProxyEntry | None:
        try:
            identifier = proxy_id if isinstance(proxy_id, uuid.UUID) else uuid.UUID(str(proxy_id))
        except ValueError:
            return None
        result = await self._session.execute(select(ProxyEntry).where(ProxyEntry.id == identifier))
        return result.scalar_one_or_none()

    async def _bound_today_ids(self) -> set[str]:
        result = await self._session.execute(
            select(ProxyBinding.proxy_id).where(ProxyBinding.bound_date == today_local())
        )
        return {str(pid) for pid in result.scalars().all()}

    async def _usage_counts(self) -> dict[str, int]:
        result = await self._session.execute(
            select(ProxyBinding.proxy_id, func.count(ProxyBinding.id)).group_by(ProxyBinding.proxy_id)
        )
        return {str(pid): int(count) for pid, count in result.all()}

    # ---------------- 抢占 ----------------

    async def _insert_binding(self, proxy: ProxyEntry, task_id: str, platform: str) -> ProxyClaim | None:
        """INSERT 一条 binding。撞唯一约束返回 None。

        必须用 begin_nested() 的 SAVEPOINT 包住：AsyncSession 撞 IntegrityError 后
        整个事务进入失败态，不隔离就会把同事务里待提交的 Job 一起拖垮。
        """
        binding = ProxyBinding(
            proxy_id=proxy.id, bound_date=today_local(), task_id=task_id,
            platform=platform, status="claimed",
        )
        try:
            async with self._session.begin_nested():
                self._session.add(binding)
        except IntegrityError:
            return None
        return ProxyClaim(proxy_url=build_proxy_url(proxy), binding_id=binding.id, proxy_id=proxy.id)

    async def claim(self, task_id: str, platform: str) -> ProxyClaim | None:
        """原子抢占一个今日未用的可用代理。池子见底返回 None。"""
        result = await self._session.execute(select(ProxyEntry))
        candidates = [p for p in result.scalars().all() if p.status in ACTIVE_STATUSES]
        by_id = {str(p.id): p for p in candidates}
        bound = await self._bound_today_ids()
        usage = await self._usage_counts()

        while True:
            allocator = DailyUniqueAllocator(LeastUsedAllocator(usage), bound)
            picked = allocator.select([{"id": str(p.id)} for p in candidates])
            if picked is None:
                return None
            proxy = by_id[picked["id"]]
            claim = await self._insert_binding(proxy, task_id, platform)
            if claim is not None:
                return claim
            bound.add(str(proxy.id))          # 被并发任务抢走，换下一个

    async def claim_specific(self, proxy_id, task_id: str, platform: str) -> ProxyClaim | None:
        """手动指定路径。该代理今日已绑返回 None（调用方转 409）。"""
        proxy = await self.get_proxy(proxy_id)
        if proxy is None:
            return None
        return await self._insert_binding(proxy, task_id, platform)

    # ---------------- 回填与收尾 ----------------

    async def mark_opened(self, task_id: str, profile_id, profile_name: str | None = None) -> None:
        await self._session.execute(
            update(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "claimed")
            .values(status="opened", profile_id=str(profile_id), profile_name=profile_name)
        )

    async def finalize(self, task_id: str, success: bool) -> None:
        """终态收尾。两条语句 WHERE 互斥，覆盖全部三种情形：
        成功 → opened 标 success，无 claimed 可删；
        失败但窗口建过 → opened 标 failed，仍占当天；
        失败且窗口没建成 → 无 opened 可标，claimed 被删，还回配额。
        """
        await self._session.execute(
            update(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "opened")
            .values(status="success" if success else "failed")
        )
        await self._session.execute(
            delete(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "claimed")
        )

    async def release_unopened(self, task_id: str) -> None:
        """崩溃恢复用：清掉从未建成窗口的占位。"""
        await self._session.execute(
            delete(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "claimed")
        )

    # ---------------- 聚合 ----------------

    async def today_summary(self) -> dict[str, dict]:
        """返回 {proxy_id: {total_bound, today_bound, today_profile_name}}。
        固定两条查询，不随代理数量增长。"""
        totals = await self._session.execute(
            select(ProxyBinding.proxy_id, func.count(ProxyBinding.id)).group_by(ProxyBinding.proxy_id)
        )
        summary = {
            str(pid): {"total_bound": int(count), "today_bound": 0, "today_profile_name": None}
            for pid, count in totals.all()
        }
        rows = await self._session.execute(
            select(ProxyBinding).where(ProxyBinding.bound_date == today_local())
        )
        for binding in rows.scalars().all():
            entry = summary.setdefault(
                str(binding.proxy_id),
                {"total_bound": 0, "today_bound": 0, "today_profile_name": None},
            )
            entry["today_bound"] = 1
            entry["today_profile_name"] = binding.profile_name
        return summary

    async def list_bindings(self, proxy_id, limit: int = 50, offset: int = 0) -> list[ProxyBinding]:
        proxy = await self.get_proxy(proxy_id)
        if proxy is None:
            return []
        result = await self._session.execute(
            select(ProxyBinding)
            .where(ProxyBinding.proxy_id == proxy.id)
            .order_by(ProxyBinding.bound_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def quota(self) -> dict[str, int]:
        total = await self._session.execute(
            select(func.count(ProxyEntry.id)).where(ProxyEntry.status.in_(ACTIVE_STATUSES))
        )
        total_count = int(total.scalar() or 0)
        used = len(await self._bound_today_ids())
        return {"total": total_count, "used_today": used,
                "available_today": max(total_count - used, 0)}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_binding_service.py -q
```
Expected: PASS，12 passed

- [ ] **Step 5: 提交**

```bash
git add services/gateway/proxy_binding_service.py services/tests/gateway/test_proxy_binding_service.py
git commit -m "feat(proxy): ProxyBindingService 原子抢占与当天绑定回填"
```

---

### Task 5: 批量导入端点

**Files:**
- Modify: `services/gateway/schemas.py`（追加）、`services/gateway/routers/proxy.py`（追加路由）
- Test: `services/tests/gateway/test_proxy_routes.py`（追加）

- [ ] **Step 1: 写失败测试**

追加到 `services/tests/gateway/test_proxy_routes.py` 末尾：

```python
# ──────────────────────────────────────────────
# POST /proxy/import
# ──────────────────────────────────────────────

def test_import_proxies_creates_entries(client):
    added = []

    class _Session:
        async def execute(self, stmt):
            class R:
                def scalars(self_inner): return self_inner
                def all(self_inner): return []
            return R()
        def add(self, obj):
            obj.id = uuid.uuid4()
            added.append(obj)
        async def flush(self): pass
        async def refresh(self, obj): pass
        async def delete(self, obj): pass

    app.dependency_overrides[get_session] = _session_override(_Session())
    r = client.post("/proxy/import", json={
        "text": "45.61.125.104:6115:proxyuser:proxypass\n136.0.186.187:6548:proxyuser:proxypass",
        "type": "http",
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["imported"] == 2 and data["duplicates"] == 0 and data["invalid"] == []
    assert added[0].type == "http" and added[0].port == 6115


def test_import_reports_invalid_lines(client):
    class _Session:
        async def execute(self, stmt):
            class R:
                def scalars(self_inner): return self_inner
                def all(self_inner): return []
            return R()
        def add(self, obj): obj.id = uuid.uuid4()
        async def flush(self): pass
        async def refresh(self, obj): pass
        async def delete(self, obj): pass

    app.dependency_overrides[get_session] = _session_override(_Session())
    r = client.post("/proxy/import", json={"text": "1.2.3.4:8080\ngarbage", "type": "http"})
    assert r.json()["data"]["imported"] == 1
    assert r.json()["data"]["invalid"][0]["line_no"] == 2


def test_import_skips_existing_host_port(client):
    existing = FakeProxyEntry(host="1.2.3.4", port=8080)
    added = []

    class _Session:
        async def execute(self, stmt):
            class R:
                def scalars(self_inner): return self_inner
                def all(self_inner): return [existing]
            return R()
        def add(self, obj):
            obj.id = uuid.uuid4()
            added.append(obj)
        async def flush(self): pass
        async def refresh(self, obj): pass
        async def delete(self, obj): pass

    app.dependency_overrides[get_session] = _session_override(_Session())
    r = client.post("/proxy/import", json={"text": "1.2.3.4:8080", "type": "http"})
    assert r.json()["data"]["imported"] == 0 and r.json()["data"]["duplicates"] == 1
    assert added == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_routes.py -q -k import
```
Expected: FAIL，404（路由不存在）

- [ ] **Step 3: 加 schema**

`services/gateway/schemas.py` 在 `ProxyStatusUpdate` 之后插入：

```python
class ProxyImportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    type: str = Field(default="http", pattern="^(http|https|socks5)$")
    skip_duplicates: bool = Field(default=True)
```

- [ ] **Step 4: 加路由**

`services/gateway/routers/proxy.py` 顶部 import 改为：

```python
from gateway.schemas import ProxyImportRequest, ProxyStatusUpdate, ProxyUpdate, ProxyWrite
```

文件末尾追加：

```python
@router.post("/proxy/import", response_model=ApiResponse)
async def import_proxies(body: ProxyImportRequest, session: AsyncSession = Depends(get_session)):
    """批量导入代理文本。按 (host, port) 去重，逐行报告非法项。"""
    from sqlalchemy import select
    from gateway.proxy_import import parse_proxy_lines

    drafts, invalid = parse_proxy_lines(body.text, body.type)

    existing: set[tuple[str, int]] = set()
    if body.skip_duplicates:
        result = await session.execute(select(ProxyEntry))
        existing = {(p.host, int(p.port)) for p in result.scalars().all()}

    imported, duplicates = 0, 0
    for draft in drafts:
        if (draft.host, draft.port) in existing:
            duplicates += 1
            continue
        session.add(ProxyEntry(
            type=draft.type, host=draft.host, port=draft.port,
            username=draft.username, password=draft.password, status="active",
        ))
        existing.add((draft.host, draft.port))
        imported += 1
    await session.flush()

    return ApiResponse(data={
        "imported": imported,
        "duplicates": duplicates,
        "invalid": [{"line_no": i.line_no, "raw": i.raw, "reason": i.reason} for i in invalid],
    })
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_routes.py -q
```
Expected: PASS，全部通过（含既有 14 个）

- [ ] **Step 6: 提交**

```bash
git add services/gateway/schemas.py services/gateway/routers/proxy.py services/tests/gateway/test_proxy_routes.py
git commit -m "feat(proxy): POST /proxy/import 批量导入，按 host:port 去重"
```

---

### Task 6: 列表聚合、明细与配额端点

**Files:**
- Modify: `services/gateway/routers/proxy.py:12-21`（`list_proxies`）、追加两个路由
- Test: `services/tests/gateway/test_proxy_routes.py`（追加）

- [ ] **Step 1: 写失败测试**

追加到 `services/tests/gateway/test_proxy_routes.py` 末尾：

```python
# ──────────────────────────────────────────────
# 绑定聚合 / 明细 / 配额
# ──────────────────────────────────────────────

def test_list_proxies_includes_binding_summary(client):
    entry = FakeProxyEntry()
    session = make_fake_session(scalars_all=[entry])
    app.dependency_overrides[get_session] = _session_override(session)

    summary = {str(entry.id): {"total_bound": 7, "today_bound": 1,
                               "today_profile_name": "a@gmail.com"}}
    with patch("gateway.proxy_binding_service.ProxyBindingService.today_summary",
               new=AsyncMock(return_value=summary)):
        r = client.get("/proxy")

    item = r.json()["data"][0]
    assert item["today_bound"] == 1 and item["total_bound"] == 7
    assert item["today_profile_name"] == "a@gmail.com"
    assert item["available_today"] is False


def test_list_proxies_defaults_when_never_bound(client):
    entry = FakeProxyEntry()
    session = make_fake_session(scalars_all=[entry])
    app.dependency_overrides[get_session] = _session_override(session)

    with patch("gateway.proxy_binding_service.ProxyBindingService.today_summary",
               new=AsyncMock(return_value={})):
        r = client.get("/proxy")

    item = r.json()["data"][0]
    assert item["today_bound"] == 0 and item["total_bound"] == 0
    assert item["available_today"] is True


def test_get_proxy_bindings_returns_rows(client):
    pid = str(uuid.uuid4())
    session = make_fake_session()
    app.dependency_overrides[get_session] = _session_override(session)

    class FakeBinding:
        bound_date = None
        profile_id = "777"
        profile_name = "a@gmail.com"
        platform = "google"
        status = "success"
        created_at = None

    with patch("gateway.proxy_binding_service.ProxyBindingService.list_bindings",
               new=AsyncMock(return_value=[FakeBinding()])):
        r = client.get(f"/proxy/{pid}/bindings")

    assert r.status_code == 200
    assert r.json()["data"][0]["profile_name"] == "a@gmail.com"


def test_proxy_quota_endpoint(client):
    session = make_fake_session()
    app.dependency_overrides[get_session] = _session_override(session)

    with patch("gateway.proxy_binding_service.ProxyBindingService.quota",
               new=AsyncMock(return_value={"total": 100, "used_today": 37, "available_today": 63})):
        r = client.get("/proxy/quota")

    assert r.json()["data"]["available_today"] == 63
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_routes.py -q -k "summary or bindings or quota"
```
Expected: FAIL — 列表缺字段；两个新端点 404

- [ ] **Step 3: 改列表路由**

把 `services/gateway/routers/proxy.py:12-21` 整段替换为：

```python
@router.get("/proxy", response_model=ApiResponse)
async def list_proxies(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    from gateway.proxy_binding_service import ProxyBindingService

    result = await session.execute(select(ProxyEntry).order_by(ProxyEntry.created_at.desc()))
    proxies = result.scalars().all()
    summary = await ProxyBindingService(session).today_summary()
    empty = {"total_bound": 0, "today_bound": 0, "today_profile_name": None}
    return ApiResponse(data=[{
        "id": str(p.id), "type": p.type, "host": p.host, "port": p.port,
        "username": p.username, "has_password": bool(p.password), "status": p.status,
        "region": p.region,
        **summary.get(str(p.id), empty),
        "available_today": summary.get(str(p.id), empty)["today_bound"] == 0,
    } for p in proxies])
```

> `/proxy/quota` 必须定义在 `/proxy/{proxy_id}` 之前，否则 `quota` 会被当成 proxy_id 匹配掉。本路由文件里 `{proxy_id}` 的路由都带后缀（`/test`、`/status`），`GET /proxy/{id}` 不存在，故追加到文件末尾即可。

- [ ] **Step 4: 加明细与配额路由**

文件末尾追加：

```python
@router.get("/proxy/quota", response_model=ApiResponse)
async def get_proxy_quota(session: AsyncSession = Depends(get_session)):
    """今日代理配额概览，供注册页展示剩余可用量。"""
    from gateway.proxy_binding_service import ProxyBindingService
    return ApiResponse(data=await ProxyBindingService(session).quota())


@router.get("/proxy/{proxy_id}/bindings", response_model=ApiResponse)
async def list_proxy_bindings(
    proxy_id: str,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """该代理绑定过的窗口明细，最近的在前。"""
    from gateway.proxy_binding_service import ProxyBindingService

    bindings = await ProxyBindingService(session).list_bindings(proxy_id, limit=limit, offset=offset)
    return ApiResponse(data=[{
        "bound_date": b.bound_date.isoformat() if b.bound_date else None,
        "profile_id": b.profile_id,
        "profile_name": b.profile_name,
        "platform": b.platform,
        "status": b.status,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    } for b in bindings])
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_proxy_routes.py tests/gateway/test_routes_inventory.py -q
```
Expected: PASS

> `test_routes_inventory.py` 若断言了路由总数或路由清单，需同步把三个新端点加进去。

- [ ] **Step 6: 提交**

```bash
git add services/gateway/routers/proxy.py services/tests/gateway/test_proxy_routes.py
git commit -m "feat(proxy): 列表返回今日/累计绑定，新增明细与配额端点"
```

---

### Task 7: 注册路由每任务各抢一个代理

**Files:**
- Modify: `services/gateway/routers/registration.py:16-49`（删旧解析）、`:52-110`（改主体）
- Test: `services/tests/gateway/test_registration_routes.py`（追加）

- [ ] **Step 1: 写失败测试**

先读 `services/tests/gateway/test_registration_routes.py` 了解既有 fixture 与 mock 方式，然后追加：

```python
# ──────────────────────────────────────────────
# 当天一 IP 一窗口
# ──────────────────────────────────────────────

def test_each_task_claims_a_distinct_proxy(client, admin_token, runtime_stub):
    """count=3 时应发生 3 次独立 claim，而非全批共用一个代理。"""
    from gateway.proxy_binding_service import ProxyClaim
    import uuid as _uuid

    claims = [ProxyClaim(f"http://p{i}:1080", _uuid.uuid4(), _uuid.uuid4()) for i in range(3)]
    with patch("gateway.proxy_binding_service.ProxyBindingService.claim",
               new=AsyncMock(side_effect=claims)):
        r = client.post("/register/google", json={"count": 3},
                        headers={"Authorization": f"Bearer {admin_token}"})

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dispatched"] == 3 and data["skipped"] == 0
    used = [c.kwargs["proxy"] for c in runtime_stub.submit_registration.call_args_list]
    assert len(set(used)) == 3


def test_partial_dispatch_when_pool_runs_out(client, admin_token, runtime_stub):
    from gateway.proxy_binding_service import ProxyClaim
    import uuid as _uuid

    side = [ProxyClaim("http://p0:1080", _uuid.uuid4(), _uuid.uuid4()), None]
    with patch("gateway.proxy_binding_service.ProxyBindingService.claim",
               new=AsyncMock(side_effect=side)):
        r = client.post("/register/google", json={"count": 5},
                        headers={"Authorization": f"Bearer {admin_token}"})

    data = r.json()["data"]
    assert data["dispatched"] == 1 and data["skipped"] == 4
    assert "1/5" in data["message"]


def test_manual_proxy_rejects_count_over_one(client, admin_token):
    r = client.post("/register/google",
                    json={"count": 2, "proxy_id": str(uuid.uuid4())},
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 422


def test_manual_proxy_conflicts_when_already_bound_today(client, admin_token):
    with patch("gateway.proxy_binding_service.ProxyBindingService.get_proxy",
               new=AsyncMock(return_value=object())), \
         patch("gateway.proxy_binding_service.ProxyBindingService.claim_specific",
               new=AsyncMock(return_value=None)):
        r = client.post("/register/google",
                        json={"count": 1, "proxy_id": str(uuid.uuid4())},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 409


def test_manual_proxy_not_found_is_404(client, admin_token):
    with patch("gateway.proxy_binding_service.ProxyBindingService.get_proxy",
               new=AsyncMock(return_value=None)):
        r = client.post("/register/google",
                        json={"count": 1, "proxy_id": str(uuid.uuid4())},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404


def test_no_available_proxy_returns_zero_dispatched(client, admin_token):
    with patch("gateway.proxy_binding_service.ProxyBindingService.claim",
               new=AsyncMock(return_value=None)):
        r = client.post("/register/google", json={"count": 2},
                        headers={"Authorization": f"Bearer {admin_token}"})
    data = r.json()["data"]
    assert data["dispatched"] == 0 and data["skipped"] == 2 and data["task_ids"] == []
```

若既有测试文件没有 `runtime_stub` fixture，在该文件内新增：

```python
@pytest.fixture
def runtime_stub():
    """替换 app.state.task_manager，避免真起子进程。"""
    from gateway.main import app as _app
    stub = MagicMock()
    stub.submit_registration = AsyncMock()
    _app.state.task_manager = stub
    yield stub
    _app.state.task_manager = None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_registration_routes.py -q -k "distinct or partial or manual or no_available"
```
Expected: FAIL — 返回体无 `dispatched` / `skipped`

- [ ] **Step 3: 删掉旧的整批解析**

删除 `services/gateway/routers/registration.py:16-49` 的 `_proxy_url` / `_pick_active_proxy` / `_resolve_proxy` 三个函数——组装连接串的职责已归 `proxy_binding_service.build_proxy_url`，重复实现会漂移。

- [ ] **Step 4: 改路由主体**

把 `trigger_registration` 内从 `proxy = await _resolve_proxy(...)` 到 `return ApiResponse(...)` 的整段（原 93-110 行）替换为：

```python
    from gateway.proxy_binding_service import ProxyBindingService

    binding_service = ProxyBindingService(session)
    if body.proxy_id:
        if body.count > 1:
            raise HTTPException(status_code=422, detail="手动指定代理时数量只能为 1")
        if await binding_service.get_proxy(body.proxy_id) is None:
            raise HTTPException(status_code=404, detail="Proxy not found")

    job_service = RegistrationJobService(session)
    task_ids: list[str] = []
    skipped = 0
    for index in range(body.count):
        task_id = str(uuid.uuid4())
        claim = (
            await binding_service.claim_specific(body.proxy_id, task_id, platform)
            if body.proxy_id
            else await binding_service.claim(task_id, platform)
        )
        if claim is None:
            if body.proxy_id:
                raise HTTPException(status_code=409, detail="该代理今日已绑定窗口")
            skipped = body.count - index      # 自动分配：池子见底，已派发的照常跑
            break
        await job_service.enqueue(task_id, platform)
        # binding 与 queued Job 必须同事务提交：否则「抢到 IP 但任务没落库」会留下
        # 永不回收的悬挂占用。提交后子进程事件才能安全地由独立会话更新该 Job。
        if session is not None:
            await session.commit()
        await runtime.submit_registration(
            task_id,
            platform=platform,
            idx=index,
            proxy=claim.proxy_url,
            config=config,
        )
        task_ids.append(task_id)

    return ApiResponse(data={
        "task_ids": task_ids,
        "status": "queued",
        "count": body.count,
        "dispatched": len(task_ids),
        "skipped": skipped,
        "message": f"当天可用 IP 不足，已启动 {len(task_ids)}/{body.count}" if skipped else None,
    })
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/gateway/test_registration_routes.py tests/gateway/test_register_mode.py -q
```
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add services/gateway/routers/registration.py services/tests/gateway/test_registration_routes.py
git commit -m "feat(register): 每个注册任务各抢一个当天未用代理，池空则部分派发"
```

---

### Task 8: worker 事件回填窗口 ID

**Files:**
- Modify: `services/worker/flows/base.py`（追加 emitter、改 `FlowRegistry.get`）
- Modify: `services/worker/tasks/registration.py:71`
- Modify: `services/worker/flows/gmail.py:41-47`
- Modify: `services/worker/local_task_manager.py`（`_handle_event` 与终态）
- Test: `services/tests/worker/test_flows_base.py`（追加）

- [ ] **Step 1: 写失败测试**

追加到 `services/tests/worker/test_flows_base.py` 末尾：

```python
# ──────────────────────────────────────────────
# TaskEventEmitter
# ──────────────────────────────────────────────

def test_queue_event_emitter_wraps_payload_with_task_context():
    from worker.flows.base import QueueEventEmitter

    sent = []
    emitter = QueueEventEmitter(sent.append, "task-1", "google")
    emitter.emit("binding", {"profile_id": "777", "profile_name": "a@gmail.com"})

    assert sent == [{"type": "binding", "task_id": "task-1", "platform": "google",
                     "profile_id": "777", "profile_name": "a@gmail.com"}]


def test_flow_registry_injects_services():
    from worker.flows.base import FlowRegistry, RegistrationFlow

    class _Flow(RegistrationFlow):
        def get_steps(self): return []

    FlowRegistry.register("unit-test-platform", _Flow)
    sentinel = object()
    assert FlowRegistry.get("unit-test-platform", services=sentinel).services is sentinel


def test_flow_registry_defaults_services_to_none():
    from worker.flows.base import FlowRegistry, RegistrationFlow

    class _Flow(RegistrationFlow):
        def get_steps(self): return []

    FlowRegistry.register("unit-test-platform-2", _Flow)
    assert FlowRegistry.get("unit-test-platform-2").services is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/worker/test_flows_base.py -q
```
Expected: FAIL — `ImportError: cannot import name 'QueueEventEmitter'`

- [ ] **Step 3: 加 emitter 并改注册表**

`services/worker/flows/base.py` 在 `class RegistrationFlow` 之前插入：

```python
class TaskEventEmitter(ABC):
    """子进程向父进程回传事件的契约。子进程不写库，一切经父进程落库。"""

    @abstractmethod
    def emit(self, event_type: str, data: dict) -> None:
        ...


class QueueEventEmitter(TaskEventEmitter):
    """把事件塞进 multiprocessing.Queue，由父进程 _handle_event 落库。"""

    def __init__(self, emit: Callable[[dict], None], task_id: str, platform: str):
        self._emit = emit
        self._task_id = task_id
        self._platform = platform

    def emit(self, event_type: str, data: dict) -> None:
        self._emit({"type": event_type, "task_id": self._task_id,
                    "platform": self._platform, **data})
```

把 `FlowRegistry.get`（第 83-88 行）替换为：

```python
    @classmethod
    def get(cls, platform: str, services: Any = None) -> RegistrationFlow:
        flow_cls = cls._flows.get(platform)
        if flow_cls is None:
            raise ValueError(f"Unknown platform: {platform}")
        return flow_cls(services)
```

- [ ] **Step 4: 注入 emitter**

`services/worker/tasks/registration.py` 第 71 行 `flow = FlowRegistry.get(platform)` 替换为：

```python
    from worker.flows.base import QueueEventEmitter

    emitter = QueueEventEmitter(emit, task_id, platform) if emit is not None else None
    flow = FlowRegistry.get(platform, services=emitter)
```

- [ ] **Step 5: gmail flow 建窗口后立刻上报**

`services/worker/flows/gmail.py` 第 41-47 行替换为（把窗口名提成变量，拿到 pid 立即 emit）：

```python
        window_name = f"gmail_{context.get('profile', {}).get('first', 'unknown')}"
        bb, pid, browser, ctx, page = await open_and_connect(
            name=window_name, p=p,
            proxy_str=context.get("proxy", ""),
        )
        context["_bb"] = bb
        context["_pid"] = pid
        context["_page"] = page
        context["_context"] = ctx
        # 必须在此刻上报：等 flow 跑完再报，子进程中途崩溃就会丢失「窗口已建成」的
        # 事实，导致父进程把已暴露给目标站点的 IP 错误地还回当天配额。
        if services is not None:
            services.emit("binding", {"profile_id": str(pid), "profile_name": window_name})
```

- [ ] **Step 5b: outlook 路径穿透遗留脚本上报**

> outlook flow **不调用** `open_and_connect`——窗口在遗留脚本 `register_outlook_standalone._register_one_browser` 内部经 `_open_ixbrowser_page` 创建，flow 拿不到 pid。需把回调穿透进去。

`register_outlook_standalone.py:2271` 的函数签名与 with 块头部改为：

```python
async def _register_one_browser(bb, idx, proxy_str, on_window=None):
    """Register via ixBrowser full browser (highest traffic, most reliable).
    Returns (email, password[, graph]) or (None, None).

    on_window: 可选回调，窗口一建成就以 profile_id 调用一次，供上层记录代理绑定。
    """
    tag = f"[#{idx}][browser]"
    try:
        async with _open_ixbrowser_page(bb, idx, proxy_str) as (page, context, _pid):
            if on_window is not None:
                on_window(_pid)
            print(f"  {tag} ixBrowser connected")
```

`services/worker/flows/outlook.py:42` 的调用改为：

```python
            def _on_window(pid):
                if services is not None:
                    services.emit("binding", {"profile_id": str(pid),
                                              "profile_name": context.get("email", "")})

            result = await _register_one_browser(bb, idx, proxy_str, on_window=_on_window)
```

对应测试追加到 `services/tests/worker/test_outlook_flow.py`：

```python
@pytest.mark.asyncio
async def test_outlook_flow_emits_binding_when_window_opens():
    """窗口一建成就上报 profile_id，不等注册跑完。"""
    from worker.flows.outlook import OutlookRegistrationFlow

    sent = []

    class _Emitter:
        def emit(self, event_type, data): sent.append((event_type, data))

    async def _fake_register(bb, idx, proxy_str, on_window=None):
        on_window(999)
        return ("a@outlook.com", "pw", None)

    flow = OutlookRegistrationFlow(_Emitter())
    with patch("common.browser_provider.get_browser_provider", return_value=object()), \
         patch("register_outlook_standalone._register_one_browser", new=_fake_register):
        await flow._step_register({"proxy": "", "idx": 0, "mode": "browser", "email": "a@outlook.com"},
                                  flow.services)

    assert sent[0][0] == "binding" and sent[0][1]["profile_id"] == "999"
```

- [ ] **Step 6: 父进程消费 binding 事件**

`services/worker/local_task_manager.py` 的 `_handle_event`，在 `elif event_type == "log":` 分支之后插入：

```python
        elif event_type == "binding":
            await self._persist_binding(
                event["task_id"], event.get("profile_id"), event.get("profile_name")
            )
```

在 `_persist_status` 之前插入两个新方法：

```python
    async def _persist_binding(
        self, task_id: str, profile_id: str | None, profile_name: str | None
    ) -> None:
        """回填窗口 ID：该 IP 当天从此永久占用。"""
        from app.core.dependencies import db
        from gateway.proxy_binding_service import ProxyBindingService

        if not profile_id:
            return
        async with db.get_session() as session:
            await ProxyBindingService(session).mark_opened(task_id, profile_id, profile_name)

    async def _finalize_binding(self, task_id: str, success: bool) -> None:
        """终态收尾：窗口建过的保留占用，没建成的还回当天配额。"""
        from app.core.dependencies import db
        from gateway.proxy_binding_service import ProxyBindingService

        async with db.get_session() as session:
            await ProxyBindingService(session).finalize(task_id, success)
```

在 `result` 分支持久化成功/失败之后、`failed` 分支之内，以及 `_fail_reaped_process` 里各加一行收尾调用：

```python
            await self._finalize_binding(task_id, success)      # result 分支，success 用该分支已有的布尔值
            await self._finalize_binding(task_id, False)        # failed 分支 / _fail_reaped_process
```

- [ ] **Step 6b: 启动时清理崩溃遗留的占位**

`local_task_manager.py` 里把未完成 Job 标记 `interrupted` 的两处（约 142 / 151 行，`event_type="interrupted"`），在标记之后各加一行——否则一次崩溃就会让若干 IP 当天永久不可用：

```python
                await self._release_binding(job["task_id"])
```

在 `_finalize_binding` 之后新增：

```python
    async def _release_binding(self, task_id: str) -> None:
        """崩溃/中断恢复：窗口从未建成的占位还回当天配额。已 opened 的保持占用。"""
        from app.core.dependencies import db
        from gateway.proxy_binding_service import ProxyBindingService

        async with db.get_session() as session:
            await ProxyBindingService(session).release_unopened(task_id)
```

对应测试追加到 `services/tests/worker/test_local_task_manager.py`：

```python
@pytest.mark.asyncio
async def test_interrupted_startup_releases_unopened_bindings():
    """API 重启把 Job 标 interrupted 时，未建成窗口的占位必须还回配额。"""
    from worker.local_task_manager import LocalTaskManager

    released = []
    manager = LocalTaskManager.__new__(LocalTaskManager)
    with patch("gateway.proxy_binding_service.ProxyBindingService.release_unopened",
               new=AsyncMock(side_effect=lambda tid: released.append(tid))):
        await manager._release_binding("task-1")

    assert released == ["task-1"]
```

- [ ] **Step 7: 跑测试确认通过**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/worker/ -q
```
Expected: PASS，全部通过

- [ ] **Step 8: 提交**

```bash
git add services/worker/ services/tests/worker/
git commit -m "feat(worker): 窗口建成即经事件流回填绑定，终态按是否建成窗口决定是否还配额"
```

---

### Task 9: `_parse_proxy` 支持显式类型

**Files:**
- Modify: `common/ixbrowser_provider.py:80-125`
- Test: `tests/test_ixbrowser_provider.py`（追加）

> **范围说明：** 本任务是防御性加固，不是本功能的阻塞项。`build_proxy_url` 始终输出带 scheme 的串（`http://user:pass@host:port`），走的是 `@` 分支，不会触发第 112-120 行把四段式硬编码成 socks5 的路径。加这个参数是为了让直接传裸四段式的调用方也能拿到正确协议。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ixbrowser_provider.py` 末尾：

```python
def test_parse_proxy_four_field_defaults_to_socks5_for_compat():
    """不传 default_type 时保持既有行为，1024proxy 调用方不受影响。"""
    assert IXBrowserProvider._parse_proxy("1.2.3.4:1080:u:p")["type"] == "socks5"


def test_parse_proxy_four_field_honours_explicit_type():
    assert IXBrowserProvider._parse_proxy("1.2.3.4:8080:u:p", default_type="http")["type"] == "http"


def test_parse_proxy_scheme_prefix_still_wins_over_default_type():
    assert IXBrowserProvider._parse_proxy("socks5://u:p@1.2.3.4:1080", default_type="http")["type"] == "socks5"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ixbrowser_provider.py -q
```
Expected: FAIL — `_parse_proxy() got an unexpected keyword argument 'default_type'`

- [ ] **Step 3: 改签名与四段式分支**

`common/ixbrowser_provider.py` 第 80-81 行改为：

```python
    @staticmethod
    def _parse_proxy(proxy_str, default_type=None):
```

第 88 行 `proxy_type = "http"` 改为：

```python
        proxy_type = default_type or "http"
        explicit = default_type is not None
```

第 111-120 行（四段式分支）改为：

```python
        # host:port:user:pass（1024proxy 格式）。调用方未显式指定类型时沿用 socks5 兼容行为。
        match3 = re.match(r'^([^:]+):(\d+):(.+):([^:]+)$', proxy_str)
        if match3:
            return {
                "type": proxy_type if explicit or proxy_type != "http" else "socks5",
                "host": match3.group(1),
                "port": match3.group(2),
                "username": match3.group(3),
                "password": match3.group(4),
            }
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ixbrowser_provider.py -q
```
Expected: PASS，全部通过（既有 11 个 + 新增 3 个）

- [ ] **Step 5: 提交**

```bash
git add common/ixbrowser_provider.py tests/test_ixbrowser_provider.py
git commit -m "fix(ixbrowser): _parse_proxy 支持显式类型，四段式不再无条件当 socks5"
```

---

### Task 10: ProxyPage 批量导入与绑定展示

**Files:**
- Modify: `frontend/src/pages/ProxyPage.tsx`
- Test: `frontend/src/pages/ProxyPage.test.tsx`（追加）

- [ ] **Step 1: 写失败测试**

该文件已有的写法是 `renderWithProviders`（来自 `@/test/utils`）+ `vi.stubGlobal('fetch', ...)`，**没有** `mockFetchOnce` 之类的辅助函数。沿用既有风格追加：

```tsx
// 追加到 frontend/src/pages/ProxyPage.test.tsx
import { fireEvent } from '@testing-library/react'

function stubFetch(rows: any[]) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ data: rows }),
  }))
}

describe('绑定展示', () => {
  it('渲染今日与累计绑定列', async () => {
    stubFetch([{ id: 'p1', type: 'http', host: '1.2.3.4', port: 8080, status: 'active',
                 today_bound: 1, total_bound: 7,
                 today_profile_name: 'a@gmail.com', available_today: false }])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => expect(screen.getByText('今日 1/1')).toBeInTheDocument())
    expect(screen.getByText('累计 7')).toBeInTheDocument()
  })

  it('未绑定过的代理显示今日 0/1', async () => {
    stubFetch([{ id: 'p1', type: 'http', host: '1.2.3.4', port: 8080, status: 'active',
                 today_bound: 0, total_bound: 0,
                 today_profile_name: null, available_today: true }])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => expect(screen.getByText('今日 0/1')).toBeInTheDocument())
  })
})

describe('批量导入', () => {
  it('渲染批量导入按钮', async () => {
    stubFetch([])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /批量导入/ })).toBeInTheDocument()
    })
  })

  it('提交后调用导入接口', async () => {
    stubFetch([])
    renderWithProviders(<ProxyPage />)
    fireEvent.click(await screen.findByRole('button', { name: /批量导入/ }))
    fireEvent.change(screen.getByPlaceholderText(/每行一条/), {
      target: { value: '1.2.3.4:8080:u:p' },
    })
    fireEvent.click(screen.getByRole('button', { name: /确 定|确定/ }))
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/proxy/import',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/frontend && npm run test -- src/pages/ProxyPage.test.tsx
```
Expected: FAIL — 找不到「今日 1/1」「批量导入」

- [ ] **Step 3: 扩展 Proxy 接口与状态**

`frontend/src/pages/ProxyPage.tsx` 的 `interface Proxy` 追加字段：

```tsx
  today_bound?: number
  total_bound?: number
  today_profile_name?: string | null
  available_today?: boolean
```

组件内新增状态：

```tsx
  const [importVisible, setImportVisible] = useState(false)
  const [importText, setImportText] = useState('')
  const [importType, setImportType] = useState('http')
  const [bindings, setBindings] = useState<Record<string, any[]>>({})
```

- [ ] **Step 4: 加导入与明细逻辑**

在 `addProxy` 之后插入：

```tsx
  const importProxies = async () => {
    try {
      const resp = await fetch('/api/proxy/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: importText, type: importType, skip_duplicates: true }),
      })
      const data = await parseResponse(resp)
      const { imported, duplicates, invalid } = data.data
      message.success(`导入 ${imported} 条，跳过重复 ${duplicates} 条，非法 ${invalid.length} 行`)
      setImportVisible(false)
      setImportText('')
      fetchProxies()
    } catch { message.error('导入失败') }
  }

  const loadBindings = async (id: string) => {
    try {
      const resp = await fetch(`/api/proxy/${id}/bindings`)
      const data = await parseResponse(resp)
      setBindings(prev => ({ ...prev, [id]: data.data || [] }))
    } catch { setBindings(prev => ({ ...prev, [id]: [] })) }
  }
```

- [ ] **Step 5: 加表格列与展开行**

在 `columns` 数组的「状态」列之前插入：

```tsx
    {
      title: '今日 / 累计', key: 'binding', width: 150,
      render: (_: any, record: Proxy) => (
        <Space size={4}>
          <Tag color={record.today_bound ? 'red' : 'green'}>今日 {record.today_bound ?? 0}/1</Tag>
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            累计 {record.total_bound ?? 0}
          </span>
        </Space>
      ),
    },
```

给 `<Table>` 加展开配置：

```tsx
        expandable={{
          onExpand: (expanded, record) => { if (expanded) loadBindings(record.id) },
          expandedRowRender: (record: Proxy) => (
            <Table
              rowKey={(r: any) => `${r.bound_date}-${r.profile_id}`}
              size="small"
              pagination={false}
              dataSource={bindings[record.id] || []}
              columns={[
                { title: '日期', dataIndex: 'bound_date', key: 'bound_date' },
                { title: '窗口 ID', dataIndex: 'profile_id', key: 'profile_id' },
                { title: '窗口名 / 邮箱', dataIndex: 'profile_name', key: 'profile_name',
                  render: (v: string) => v || '-' },
                { title: '平台', dataIndex: 'platform', key: 'platform' },
                { title: '结果', dataIndex: 'status', key: 'status' },
              ]}
            />
          ),
        }}
```

- [ ] **Step 6: 加导入按钮与 Modal**

在「添加代理」按钮之前插入：

```tsx
          <Button onClick={() => setImportVisible(true)}>批量导入</Button>
```

顶部统计条改为（在已激活计数之后追加今日可用）：

```tsx
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            已激活 {proxies.filter(p => p.active !== false).length} / {proxies.length}
            ｜今日可用 {proxies.filter(p => p.available_today !== false).length} / {proxies.length}
          </span>
```

在「编辑代理」Modal 之后追加：

```tsx
      <Modal title="批量导入代理" open={importVisible} onOk={importProxies}
             onCancel={() => setImportVisible(false)} width={640}>
        <Select
          value={importType}
          onChange={setImportType}
          style={{ width: 160, marginBottom: 12 }}
          options={[{ value: 'http', label: 'HTTP' }, { value: 'socks5', label: 'SOCKS5' }]}
        />
        <Input.TextArea
          rows={12}
          value={importText}
          onChange={e => setImportText(e.target.value)}
          placeholder={'每行一条，支持：\nhost:port:user:pass\nuser:pass@host:port\nhost:port'}
        />
      </Modal>
```

- [ ] **Step 7: 跑测试确认通过**

```bash
cd F:/reg-factory/frontend && npm run test -- src/pages/ProxyPage.test.tsx
```
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/ProxyPage.tsx frontend/src/pages/ProxyPage.test.tsx
git commit -m "feat(frontend): 代理页批量导入、今日/累计绑定列与明细展开"
```

---

### Task 11: AccountsPage 代理选择约束

**Files:**
- Modify: `frontend/src/pages/AccountsPage.tsx:74`、`:151`、`:501-516`
- Test: `frontend/src/pages/AccountsPage.test.tsx`（追加）

- [ ] **Step 1: 写失败测试**

该文件已有本地 `renderAccountsPage()` 辅助（`ThemeProvider` + `MemoryRouter` + `/accounts/:platform` 路由）与 `vi.stubGlobal('fetch', ...)`。沿用既有风格追加：

```tsx
// 追加到 frontend/src/pages/AccountsPage.test.tsx
import { fireEvent } from '@testing-library/react'

/** 按 URL 分派响应：账号列表与代理列表结构不同。 */
function stubFetchByUrl(proxies: any[], registerResult?: any) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, init?: any) => {
    if (typeof url === 'string' && url.startsWith('/api/proxy')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: proxies }) })
    }
    if (init?.method === 'POST' && typeof url === 'string' && url.includes('/register/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(registerResult) })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: [], total: 0 } }) })
  }))
}

describe('代理选择约束', () => {
  it('今日已用的代理在下拉中标记并禁用', async () => {
    stubFetchByUrl([{ id: 'p1', host: '1.2.3.4', port: 8080, status: 'active',
                      today_bound: 1, available_today: false }])
    renderAccountsPage()
    fireEvent.mouseDown(await screen.findByText(/自动选择/))
    await waitFor(() => {
      expect(screen.getByText(/1\.2\.3\.4:8080（今日已用）/)).toBeInTheDocument()
    })
    expect(document.querySelector('.ant-select-item-option-disabled')).toBeTruthy()
  })

  it('可用代理不带已用后缀', async () => {
    stubFetchByUrl([{ id: 'p1', host: '1.2.3.4', port: 8080, status: 'active',
                      today_bound: 0, available_today: true }])
    renderAccountsPage()
    fireEvent.mouseDown(await screen.findByText(/自动选择/))
    await waitFor(() => {
      expect(screen.getByText('1.2.3.4:8080')).toBeInTheDocument()
    })
  })
})
```

> 「选中后数量锁为 1」与「部分派发 warning」依赖 antd `message` 与受控 Select 的交互，在 jsdom 下断言脆弱。这两条改由 Task 12 的手工验收覆盖（见完成标准），此处不写自动化测试——**宁可不测，也不写会假绿的测试**。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory/frontend && npm run test -- src/pages/AccountsPage.test.tsx
```
Expected: FAIL

- [ ] **Step 3: 下拉禁用已用代理**

第 501-516 行的代理下拉，把 options 构造改为：

```tsx
                options={[
                  { value: '', label: '🎲 自动选择（从今日未用的已激活代理中分配）' },
                  ...proxies.map((p: any) => ({
                    value: p.id,
                    label: p.available_today === false
                      ? `${p.host}:${p.port}（今日已用）`
                      : `${p.host}:${p.port}`,
                    disabled: p.available_today === false,
                  })),
                ]}
```

- [ ] **Step 4: 选中具体代理时锁数量**

在 `selectedProxyId` 状态之后加受控逻辑，数量输入框改为：

```tsx
              <Input
                aria-label="数量"
                type="number"
                min={1}
                max={20}
                disabled={!!selectedProxyId}
                value={selectedProxyId ? 1 : registerCount}
                onChange={e => setRegisterCount(Number(e.target.value))}
              />
```

并在下拉 `onChange` 里同步：

```tsx
                onChange={(v) => { setSelectedProxyId(v); if (v) setRegisterCount(1) }}
```

- [ ] **Step 5: 展示部分派发提示**

第 151 行的注册请求，响应处理改为：

```tsx
      const data = await parseResponse(resp)
      if (data.data?.message) {
        message.warning(data.data.message)
      } else {
        message.success(`已启动 ${data.data?.dispatched ?? registerCount} 个注册任务`)
      }
```

- [ ] **Step 6: 跑测试确认通过**

```bash
cd F:/reg-factory/frontend && npm run test -- src/pages/AccountsPage.test.tsx
```
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add frontend/src/pages/AccountsPage.tsx frontend/src/pages/AccountsPage.test.tsx
git commit -m "feat(frontend): 注册页禁选今日已用代理、手动指定锁数量、部分派发提示"
```

---

### Task 12: 全量校验与导入 100 条实际数据

**Files:** 无代码改动

> **需要显式授权：** 本任务会真实写入 100 条代理记录，且需要本机服务在跑。执行前先向用户确认。

- [ ] **Step 1: 跑全部后端测试**

```bash
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m pytest tests/ -q
```
Expected: 全绿，无 ERROR

- [ ] **Step 2: 跑全部前端测试**

```bash
cd F:/reg-factory/frontend && npm run test -- --run
```
Expected: 全绿

- [ ] **Step 3: 重建前端并启动服务**

```bash
cd F:/reg-factory/frontend && npm run build
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m alembic upgrade head
cd F:/reg-factory/services && ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

- [ ] **Step 4: 导入 100 条 Webshare 代理**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -c "
import json, urllib.request
text = open('Webshare_100_proxies.txt', encoding='utf-8').read()
req = urllib.request.Request('http://127.0.0.1:8000/proxy/import',
    data=json.dumps({'text': text, 'type': 'http', 'skip_duplicates': True}).encode(),
    headers={'Content-Type': 'application/json'})
print(json.load(urllib.request.urlopen(req))['data'])
"
```
Expected: `{'imported': 100, 'duplicates': 0, 'invalid': []}`

- [ ] **Step 5: 验证配额与列表**

```bash
curl -s http://127.0.0.1:8000/proxy/quota
```
Expected: `{"total": 100, "used_today": 0, "available_today": 100}`（若库中原有代理，total 相应更大）

- [ ] **Step 6: 提交收尾**

```bash
git add -A && git commit -m "chore(proxy): 导入 Webshare 100 条静态 HTTP 代理"
```

---

## 完成标准

- [ ] `services/.venv/Scripts/python.exe -m pytest tests/ -q` 全绿
- [ ] `npm run test -- --run` 全绿
- [ ] 代理页能看到 100 条代理，每行显示「今日 0/1｜累计 0」
- [ ] 提交 count=3 的注册后，3 个任务各绑不同 IP，对应行变「今日 1/1」
- [ ] 池子用尽时提交 count=N 返回「当天可用 IP 不足，已启动 n/N」
- [ ] 手动指定今日已用的代理返回 409
- [ ] 展开代理行能看到该 IP 绑过的窗口明细
- [ ] 手工验收：注册页选中某个具体代理后，数量输入框变灰且固定为 1
- [ ] 手工验收：池子不足时提交，页面弹出「当天可用 IP 不足，已启动 n/N」的 warning
