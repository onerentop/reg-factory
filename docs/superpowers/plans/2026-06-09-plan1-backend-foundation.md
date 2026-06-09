# Plan 1: 后端基础（shared 库 + Config Service）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建微服务后端基础设施——共享基础库、数据库连接、Config Service、Docker 开发环境，使后续每个微服务都能通过继承 BaseService 零配置获得日志、认证、配置热更新等能力。

**Architecture:** 基于 Python FastAPI 的微服务架构，所有服务继承 `BaseService` 模板方法模式，共享库提供数据库（SQLAlchemy + PgBouncer）、认证（JWT + API Key 策略模式）、日志（异步批量写入）、HTTP 客户端（熔断器模式）、配置热更新（观察者模式）等横切关注点。Config Service 是第一个落地的微服务，验证整套基础设施。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL 16, Redis 7, PgBouncer, Docker Compose, pytest + pytest-asyncio

**关键设计原则：**
- 类小而专（单一职责，< 200 行）
- 面向对象：抽象基类定义接口，子类实现具体行为
- 设计模式落实到每个类
- TDD：先写测试，再写实现

---

## 文件结构

```
services/
├── shared/
│   ├── __init__.py
│   ├── database.py              — 数据库引擎工厂 + 会话管理器（工厂模式）
│   ├── base_model.py            — ORM 基类，含公共字段（模板方法）
│   ├── base_schema.py           — Pydantic 基类：分页、响应信封、错误码
│   ├── base_service.py          — FastAPI 应用工厂（模板方法 + 建造者模式）
│   ├── base_repository.py       — 通用 CRUD 仓储基类（仓储模式）
│   ├── log_handler.py           — 异步批量日志写入器（生产者-消费者模式）
│   ├── log_models.py            — 日志 ORM 模型（独立，避免循环引用）
│   ├── config_client.py         — 配置热更新客户端（观察者模式）
│   ├── http_client.py           — HTTP 客户端（熔断器模式 + 单例）
│   ├── circuit_breaker.py       — 熔断器状态机（状态模式）
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── base.py              — 认证策略接口（策略模式）
│   │   ├── jwt_strategy.py      — JWT 认证实现
│   │   ├── api_key_strategy.py  — API Key 认证实现
│   │   └── middleware.py        — FastAPI 认证中间件（组合策略）
│   ├── audit.py                 — 审计装饰器（装饰器模式）
│   └── concurrency.py           — DynamicSemaphore（线程安全信号量）
│
├── config_service/
│   ├── __init__.py
│   ├── main.py                  — 入口，继承 BaseService
│   ├── models.py                — ConfigEntry + ConfigVersion ORM
│   ├── schemas.py               — 请求/响应 Pydantic 模型
│   ├── repository.py            — 配置数据访问（继承 BaseRepository）
│   ├── service.py               — 配置业务逻辑（读/写/版本/通知）
│   ├── router.py                — FastAPI 路由
│   └── notifier.py              — Redis Pub/Sub 配置变更通知器
│
├── tests/
│   ├── conftest.py              — pytest fixtures（DB/Redis/Client）
│   ├── shared/
│   │   ├── test_database.py
│   │   ├── test_base_model.py
│   │   ├── test_base_schema.py
│   │   ├── test_base_repository.py
│   │   ├── test_circuit_breaker.py
│   │   ├── test_concurrency.py
│   │   ├── test_log_handler.py
│   │   └── test_auth.py
│   └── config_service/
│       ├── test_models.py
│       ├── test_repository.py
│       ├── test_service.py
│       └── test_router.py
│
├── migrations/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
│
├── pyproject.toml
├── docker-compose.dev.yml
└── .env.example
```

---

### Task 1: 项目脚手架 + Docker 开发环境

**Files:**
- Create: `services/pyproject.toml`
- Create: `services/.env.example`
- Create: `docker-compose.dev.yml`
- Create: `services/shared/__init__.py`
- Create: `services/config_service/__init__.py`
- Create: `services/tests/__init__.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
# services/pyproject.toml
[project]
name = "reg-factory-services"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "redis>=5.0.0",
    "httpx>=0.27.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "celery[redis]>=5.4.0",
    "gevent>=24.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "aiosqlite>=0.20.0",
]
```

- [ ] **Step 2: 创建 .env.example**

```env
# services/.env.example
DATABASE_URL=postgresql+asyncpg://regfactory:regfactory@localhost:5432/regfactory
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
CONFIG_SERVICE_URL=http://localhost:8003
```

- [ ] **Step 3: 创建 docker-compose.dev.yml**

```yaml
# docker-compose.dev.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: regfactory
      POSTGRES_PASSWORD: regfactory
      POSTGRES_DB: regfactory
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U regfactory"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
```

- [ ] **Step 4: 启动 Docker 并验证**

Run: `docker-compose -f docker-compose.dev.yml up -d`
Run: `docker-compose -f docker-compose.dev.yml ps`
Expected: postgres 和 redis 均 healthy

- [ ] **Step 5: 安装依赖**

Run: `cd services && pip install -e ".[dev]"`
Expected: 无错误

- [ ] **Step 6: 创建包初始化文件**

```python
# services/shared/__init__.py
# services/config_service/__init__.py
# services/tests/__init__.py
# services/tests/shared/__init__.py
# services/tests/config_service/__init__.py
```

- [ ] **Step 7: Commit**

```bash
git add services/ docker-compose.dev.yml
git commit -m "chore: scaffold project structure with Docker dev environment"
```

---

### Task 2: 数据库连接（工厂模式 + 会话管理器）

**设计模式：** 工厂模式（create_engine）、上下文管理器（会话生命周期）

**Files:**
- Create: `services/shared/database.py`
- Create: `services/tests/shared/test_database.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/shared/test_database.py
import pytest
from shared.database import DatabaseManager


@pytest.fixture
def db_manager():
    return DatabaseManager(url="sqlite+aiosqlite:///")


@pytest.mark.asyncio
async def test_create_engine(db_manager):
    """DatabaseManager 应该创建异步引擎"""
    engine = db_manager.engine
    assert engine is not None
    assert engine.url.drivername == "sqlite+aiosqlite"


@pytest.mark.asyncio
async def test_session_context_manager(db_manager):
    """get_session 应该返回异步上下文管理器"""
    async with db_manager.get_session() as session:
        assert session is not None
        assert session.is_active


@pytest.mark.asyncio
async def test_engine_singleton(db_manager):
    """多次访问 engine 应返回同一实例（单例）"""
    engine1 = db_manager.engine
    engine2 = db_manager.engine
    assert engine1 is engine2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/shared/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.database'`

- [ ] **Step 3: 实现 DatabaseManager**

```python
# services/shared/database.py
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseManager:
    """数据库连接管理器。
    
    工厂模式：封装引擎创建逻辑。
    单例：同一 Manager 实例共享一个 engine。
    上下文管理器：自动管理会话生命周期。
    """

    def __init__(self, url: str, echo: bool = False, pool_size: int = 20):
        self._url = url
        self._echo = echo
        self._pool_size = pool_size
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(
                self._url,
                echo=self._echo,
                pool_size=self._pool_size if "sqlite" not in self._url else 0,
                pool_pre_ping=True,
            )
            self._session_factory = async_sessionmaker(
                self._engine, expire_on_commit=False
            )
        return self._engine

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        _ = self.engine  # ensure initialized
        assert self._session_factory is not None
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/shared/test_database.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/shared/database.py services/tests/shared/test_database.py
git commit -m "feat(shared): add DatabaseManager with factory pattern and session context manager"
```

---

### Task 3: ORM 基类（模板方法模式）

**设计模式：** 模板方法（子类继承公共字段和行为）

**Files:**
- Create: `services/shared/base_model.py`
- Create: `services/tests/shared/test_base_model.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/shared/test_base_model.py
import pytest
from sqlalchemy import Column, String
from shared.base_model import BaseModel, TimestampMixin


class SampleModel(TimestampMixin, BaseModel):
    __tablename__ = "sample"
    __table_args__ = {"schema": "test"}
    name = Column(String(100))


def test_base_model_has_id():
    """BaseModel 应该自动提供 UUID 主键"""
    cols = {c.name for c in SampleModel.__table__.columns}
    assert "id" in cols


def test_timestamp_mixin_has_timestamps():
    """TimestampMixin 应该提供 created_at 和 updated_at"""
    cols = {c.name for c in SampleModel.__table__.columns}
    assert "created_at" in cols
    assert "updated_at" in cols


def test_model_has_schema():
    """模型应支持 schema 隔离"""
    assert SampleModel.__table__.schema == "test"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/shared/test_base_model.py -v`
Expected: FAIL

- [ ] **Step 3: 实现基类**

```python
# services/shared/base_model.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BaseModel(DeclarativeBase):
    """所有 ORM 模型的基类。提供 UUID 主键。"""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"


class TimestampMixin:
    """时间戳混入。子类自动获得 created_at / updated_at。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/shared/test_base_model.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/shared/base_model.py services/tests/shared/test_base_model.py
git commit -m "feat(shared): add BaseModel and TimestampMixin with UUID primary key"
```

---

### Task 4: Pydantic 基类（值对象模式）

**设计模式：** 值对象（不可变数据载体）、泛型（类型安全分页）

**Files:**
- Create: `services/shared/base_schema.py`
- Create: `services/tests/shared/test_base_schema.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/shared/test_base_schema.py
from shared.base_schema import (
    PaginationParams,
    PaginatedResponse,
    ApiResponse,
    ErrorResponse,
)


def test_pagination_defaults():
    p = PaginationParams()
    assert p.page == 1
    assert p.page_size == 20


def test_pagination_clamp():
    p = PaginationParams(page=0, page_size=200)
    assert p.page == 1
    assert p.page_size == 100


def test_api_response_success():
    resp = ApiResponse(data={"key": "value"})
    assert resp.success is True
    assert resp.data == {"key": "value"}


def test_paginated_response():
    resp = PaginatedResponse(
        items=["a", "b"],
        total=10,
        page=1,
        page_size=2,
    )
    assert resp.total_pages == 5
    assert resp.has_next is True
    assert resp.has_prev is False


def test_error_response():
    resp = ErrorResponse(code="NOT_FOUND", message="not found")
    assert resp.success is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/shared/test_base_schema.py -v`
Expected: FAIL

- [ ] **Step 3: 实现基类**

```python
# services/shared/base_schema.py
import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class PaginationParams(BaseModel):
    """分页参数值对象。自动约束边界。"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def clamp_values(self) -> "PaginationParams":
        object.__setattr__(self, "page", max(1, self.page))
        object.__setattr__(self, "page_size", min(100, max(1, self.page_size)))
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应信封。泛型支持任意 item 类型。"""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.page_size) if self.page_size > 0 else 0

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    model_config = {"from_attributes": True}


class ApiResponse(BaseModel):
    """统一 API 响应信封。"""

    success: bool = True
    data: Any = None
    message: str | None = None


class ErrorResponse(BaseModel):
    """错误响应。"""

    success: bool = False
    code: str
    message: str
    details: dict[str, Any] | None = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/shared/test_base_schema.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/shared/base_schema.py services/tests/shared/test_base_schema.py
git commit -m "feat(shared): add Pydantic base schemas with pagination and response envelope"
```

---

### Task 5: 通用仓储基类（仓储模式 + 泛型）

**设计模式：** 仓储模式（数据访问抽象）、泛型（类型安全 CRUD）

**Files:**
- Create: `services/shared/base_repository.py`
- Create: `services/tests/shared/test_base_repository.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/shared/test_base_repository.py
import pytest
import uuid
from sqlalchemy import Column, String
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_model import BaseModel, TimestampMixin
from shared.base_repository import BaseRepository
from shared.database import DatabaseManager


class FakeEntity(TimestampMixin, BaseModel):
    __tablename__ = "fake_entity"
    name = Column(String(100), nullable=False)


class FakeRepository(BaseRepository[FakeEntity]):
    model_class = FakeEntity


@pytest.fixture
async def db():
    manager = DatabaseManager(url="sqlite+aiosqlite:///")
    async with manager.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield manager
    await manager.close()


@pytest.fixture
async def repo(db):
    async with db.get_session() as session:
        yield FakeRepository(session)


@pytest.mark.asyncio
async def test_create_and_get(db):
    async with db.get_session() as session:
        repo = FakeRepository(session)
        entity = await repo.create(name="test")
        assert entity.id is not None
        assert entity.name == "test"

    async with db.get_session() as session:
        repo = FakeRepository(session)
        found = await repo.get_by_id(entity.id)
        assert found is not None
        assert found.name == "test"


@pytest.mark.asyncio
async def test_list_with_pagination(db):
    async with db.get_session() as session:
        repo = FakeRepository(session)
        for i in range(5):
            await repo.create(name=f"item_{i}")

    async with db.get_session() as session:
        repo = FakeRepository(session)
        items, total = await repo.list_paginated(page=1, page_size=2)
        assert len(items) == 2
        assert total == 5


@pytest.mark.asyncio
async def test_delete(db):
    async with db.get_session() as session:
        repo = FakeRepository(session)
        entity = await repo.create(name="to_delete")
        eid = entity.id

    async with db.get_session() as session:
        repo = FakeRepository(session)
        deleted = await repo.delete(eid)
        assert deleted is True

    async with db.get_session() as session:
        repo = FakeRepository(session)
        found = await repo.get_by_id(eid)
        assert found is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/shared/test_base_repository.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 BaseRepository**

```python
# services/shared/base_repository.py
import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_model import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """通用仓储基类。子类设置 model_class 即可获得完整 CRUD。

    仓储模式：将数据访问逻辑从业务逻辑中分离。
    泛型：保证类型安全，IDE 可正确推导返回类型。
    """

    model_class: type[T]

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, **kwargs: Any) -> T:
        entity = self.model_class(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: uuid.UUID) -> T | None:
        stmt = select(self.model_class).where(
            self.model_class.id == entity_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_paginated(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[T], int]:
        offset = (page - 1) * page_size

        count_stmt = select(func.count()).select_from(self.model_class)
        total = (await self._session.execute(count_stmt)).scalar_one()

        items_stmt = (
            select(self.model_class)
            .offset(offset)
            .limit(page_size)
        )
        result = await self._session.execute(items_stmt)
        items = list(result.scalars().all())

        return items, total

    async def update(self, entity_id: uuid.UUID, **kwargs: Any) -> T | None:
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return None
        for key, value in kwargs.items():
            setattr(entity, key, value)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity_id: uuid.UUID) -> bool:
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False
        await self._session.delete(entity)
        await self._session.flush()
        return True
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/shared/test_base_repository.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/shared/base_repository.py services/tests/shared/test_base_repository.py
git commit -m "feat(shared): add generic BaseRepository with CRUD and pagination"
```

---

### Task 6: 熔断器（状态模式）

**设计模式：** 状态模式（Closed → Open → HalfOpen 三态切换）

**Files:**
- Create: `services/shared/circuit_breaker.py`
- Create: `services/tests/shared/test_circuit_breaker.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/shared/test_circuit_breaker.py
import pytest
import asyncio
from shared.circuit_breaker import CircuitBreaker, CircuitState


@pytest.mark.asyncio
async def test_starts_closed():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_rejects_when_open():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


@pytest.mark.asyncio
async def test_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    await asyncio.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True


@pytest.mark.asyncio
async def test_closes_on_success_in_half_open():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    await asyncio.sleep(0.15)
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/shared/test_circuit_breaker.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 CircuitBreaker**

```python
# services/shared/circuit_breaker.py
import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """熔断器。状态模式实现三态切换。

    CLOSED: 正常通行，记录失败次数
    OPEN: 拒绝请求，等待恢复超时
    HALF_OPEN: 允许一次探测请求
    """

    def __init__(
        self, failure_threshold: int = 5, recovery_timeout: float = 30.0
    ):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._state = CircuitState.CLOSED

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/shared/test_circuit_breaker.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/shared/circuit_breaker.py services/tests/shared/test_circuit_breaker.py
git commit -m "feat(shared): add CircuitBreaker with state pattern (Closed/Open/HalfOpen)"
```

---

### Task 7: DynamicSemaphore（线程安全并发控制）

**设计模式：** Monitor 模式（线程安全）

**Files:**
- Create: `services/shared/concurrency.py`
- Create: `services/tests/shared/test_concurrency.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/shared/test_concurrency.py
import pytest
import asyncio
from shared.concurrency import DynamicSemaphore


@pytest.mark.asyncio
async def test_basic_acquire_release():
    sem = DynamicSemaphore(2)
    async with sem:
        assert sem.active == 1
    assert sem.active == 0


@pytest.mark.asyncio
async def test_blocks_at_limit():
    sem = DynamicSemaphore(1)
    acquired = []

    async def worker(name: str):
        async with sem:
            acquired.append(name)
            await asyncio.sleep(0.05)

    t1 = asyncio.create_task(worker("a"))
    await asyncio.sleep(0.01)
    assert sem.active == 1

    t2 = asyncio.create_task(worker("b"))
    await asyncio.sleep(0.01)
    assert sem.waiting == 1

    await asyncio.gather(t1, t2)
    assert sem.active == 0


@pytest.mark.asyncio
async def test_resize_expand():
    sem = DynamicSemaphore(1)
    sem.resize(3)
    assert sem.max_size == 3


@pytest.mark.asyncio
async def test_resize_shrink_no_interrupt():
    sem = DynamicSemaphore(3)
    async with sem:
        sem.resize(1)
        assert sem.max_size == 1
        assert sem.active == 1  # running task not interrupted


@pytest.mark.asyncio
async def test_status():
    sem = DynamicSemaphore(5)
    status = sem.status()
    assert status["max"] == 5
    assert status["active"] == 0
    assert status["waiting"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/shared/test_concurrency.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 DynamicSemaphore**

```python
# services/shared/concurrency.py
import asyncio


class DynamicSemaphore:
    """可运行时调整大小的异步信号量。

    扩容：立即释放差额槽位。
    缩容：不中断运行中任务，自然过渡。
    """

    def __init__(self, max_size: int):
        self._max_size = max_size
        self._semaphore = asyncio.Semaphore(max_size)
        self._active = 0
        self._waiting = 0

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def active(self) -> int:
        return self._active

    @property
    def waiting(self) -> int:
        return self._waiting

    def resize(self, new_max: int) -> None:
        if new_max < 1:
            new_max = 1
        diff = new_max - self._max_size
        self._max_size = new_max
        if diff > 0:
            for _ in range(diff):
                self._semaphore.release()
        elif diff < 0:
            for _ in range(-diff):
                self._semaphore._value = max(0, self._semaphore._value - 1)

    def status(self) -> dict:
        return {
            "max": self._max_size,
            "active": self._active,
            "waiting": self._waiting,
        }

    async def __aenter__(self) -> "DynamicSemaphore":
        self._waiting += 1
        await self._semaphore.acquire()
        self._waiting -= 1
        self._active += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._active -= 1
        self._semaphore.release()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/shared/test_concurrency.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/shared/concurrency.py services/tests/shared/test_concurrency.py
git commit -m "feat(shared): add DynamicSemaphore with runtime resize support"
```

---

### Task 8: 认证策略（策略模式）

**设计模式：** 策略模式（JWT / API Key 可切换）、组合模式（中间件组合多策略）

**Files:**
- Create: `services/shared/auth/__init__.py`
- Create: `services/shared/auth/base.py`
- Create: `services/shared/auth/jwt_strategy.py`
- Create: `services/shared/auth/api_key_strategy.py`
- Create: `services/shared/auth/middleware.py`
- Create: `services/tests/shared/test_auth.py`

- [ ] **Step 1: 写失败测试**

```python
# services/tests/shared/test_auth.py
import pytest
from shared.auth.base import AuthResult
from shared.auth.jwt_strategy import JwtAuthStrategy
from shared.auth.api_key_strategy import ApiKeyAuthStrategy


def test_jwt_encode_decode():
    strategy = JwtAuthStrategy(secret="test-secret", algorithm="HS256")
    token = strategy.create_token(user_id="user-1", role="admin")
    result = strategy.verify(token)
    assert result.authenticated is True
    assert result.user_id == "user-1"
    assert result.role == "admin"


def test_jwt_invalid_token():
    strategy = JwtAuthStrategy(secret="test-secret", algorithm="HS256")
    result = strategy.verify("invalid-token")
    assert result.authenticated is False


def test_api_key_valid():
    keys = {"key-123": {"user_id": "svc-1", "role": "service", "scopes": ["sms"]}}
    strategy = ApiKeyAuthStrategy(keys=keys)
    result = strategy.verify("key-123")
    assert result.authenticated is True
    assert result.user_id == "svc-1"
    assert "sms" in result.scopes


def test_api_key_invalid():
    strategy = ApiKeyAuthStrategy(keys={})
    result = strategy.verify("nonexistent")
    assert result.authenticated is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/shared/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: 实现认证策略**

```python
# services/shared/auth/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AuthResult:
    """认证结果值对象。"""
    authenticated: bool
    user_id: str = ""
    role: str = ""
    scopes: list[str] = field(default_factory=list)
    error: str = ""


class AuthStrategy(ABC):
    """认证策略接口。所有认证方式实现此接口。"""

    @abstractmethod
    def verify(self, credential: str) -> AuthResult:
        ...
```

```python
# services/shared/auth/jwt_strategy.py
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from shared.auth.base import AuthResult, AuthStrategy


class JwtAuthStrategy(AuthStrategy):
    """JWT 认证策略。"""

    def __init__(
        self, secret: str, algorithm: str = "HS256", expire_minutes: int = 1440
    ):
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    def create_token(self, user_id: str, role: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self._expire_minutes)
        payload = {"sub": user_id, "role": role, "exp": expire}
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify(self, credential: str) -> AuthResult:
        try:
            payload = jwt.decode(
                credential, self._secret, algorithms=[self._algorithm]
            )
            return AuthResult(
                authenticated=True,
                user_id=payload.get("sub", ""),
                role=payload.get("role", ""),
            )
        except JWTError as e:
            return AuthResult(authenticated=False, error=str(e))
```

```python
# services/shared/auth/api_key_strategy.py
from shared.auth.base import AuthResult, AuthStrategy


class ApiKeyAuthStrategy(AuthStrategy):
    """API Key 认证策略。从内存字典或数据库查找 Key。"""

    def __init__(self, keys: dict[str, dict]):
        self._keys = keys

    def verify(self, credential: str) -> AuthResult:
        key_info = self._keys.get(credential)
        if key_info is None:
            return AuthResult(authenticated=False, error="Invalid API key")
        return AuthResult(
            authenticated=True,
            user_id=key_info.get("user_id", ""),
            role=key_info.get("role", "service"),
            scopes=key_info.get("scopes", []),
        )
```

```python
# services/shared/auth/__init__.py
from shared.auth.base import AuthResult, AuthStrategy
from shared.auth.jwt_strategy import JwtAuthStrategy
from shared.auth.api_key_strategy import ApiKeyAuthStrategy

__all__ = [
    "AuthResult", "AuthStrategy",
    "JwtAuthStrategy", "ApiKeyAuthStrategy",
]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/shared/test_auth.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add services/shared/auth/ services/tests/shared/test_auth.py
git commit -m "feat(shared): add auth strategies (JWT + API Key) with strategy pattern"
```

---

### Task 9: Config Service 模型 + 仓储

**Files:**
- Create: `services/config_service/models.py`
- Create: `services/config_service/repository.py`
- Create: `services/tests/config_service/test_models.py`
- Create: `services/tests/config_service/test_repository.py`

- [ ] **Step 1: 写模型测试**

```python
# services/tests/config_service/test_models.py
from config_service.models import ConfigEntry, ConfigVersion


def test_config_entry_fields():
    cols = {c.name for c in ConfigEntry.__table__.columns}
    assert "key" in cols
    assert "value" in cols
    assert "category" in cols
    assert "description" in cols


def test_config_version_fields():
    cols = {c.name for c in ConfigVersion.__table__.columns}
    assert "config_key" in cols
    assert "old_value" in cols
    assert "new_value" in cols
    assert "changed_by" in cols
```

- [ ] **Step 2: 实现模型**

```python
# services/config_service/models.py
from sqlalchemy import Column, String, Text, JSON

from shared.base_model import BaseModel, TimestampMixin


class ConfigEntry(TimestampMixin, BaseModel):
    __tablename__ = "config_entries"
    __table_args__ = {"schema": "config"}

    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False, default=dict)
    category = Column(String(100), nullable=False, default="general")
    description = Column(Text, nullable=True)


class ConfigVersion(TimestampMixin, BaseModel):
    __tablename__ = "config_versions"
    __table_args__ = {"schema": "config"}

    config_key = Column(String(255), nullable=False, index=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=False)
    changed_by = Column(String(100), nullable=False, default="system")
```

- [ ] **Step 3: 写仓储测试**

```python
# services/tests/config_service/test_repository.py
import pytest
from shared.database import DatabaseManager
from shared.base_model import BaseModel
from config_service.models import ConfigEntry
from config_service.repository import ConfigRepository


@pytest.fixture
async def db():
    manager = DatabaseManager(url="sqlite+aiosqlite:///")
    async with manager.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_upsert_creates_new(db):
    async with db.get_session() as session:
        repo = ConfigRepository(session)
        entry = await repo.upsert("test.key", {"val": 1}, "test")
        assert entry.key == "test.key"
        assert entry.value == {"val": 1}


@pytest.mark.asyncio
async def test_upsert_updates_existing(db):
    async with db.get_session() as session:
        repo = ConfigRepository(session)
        await repo.upsert("test.key", {"val": 1}, "test")

    async with db.get_session() as session:
        repo = ConfigRepository(session)
        entry = await repo.upsert("test.key", {"val": 2}, "test")
        assert entry.value == {"val": 2}


@pytest.mark.asyncio
async def test_get_by_key(db):
    async with db.get_session() as session:
        repo = ConfigRepository(session)
        await repo.upsert("my.key", {"a": "b"}, "test")

    async with db.get_session() as session:
        repo = ConfigRepository(session)
        entry = await repo.get_by_key("my.key")
        assert entry is not None
        assert entry.value == {"a": "b"}


@pytest.mark.asyncio
async def test_get_by_category(db):
    async with db.get_session() as session:
        repo = ConfigRepository(session)
        await repo.upsert("sms.key1", {}, "sms")
        await repo.upsert("sms.key2", {}, "sms")
        await repo.upsert("proxy.key1", {}, "proxy")

    async with db.get_session() as session:
        repo = ConfigRepository(session)
        entries = await repo.get_by_category("sms")
        assert len(entries) == 2
```

- [ ] **Step 4: 实现仓储**

```python
# services/config_service/repository.py
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_repository import BaseRepository
from config_service.models import ConfigEntry, ConfigVersion


class ConfigRepository(BaseRepository[ConfigEntry]):
    model_class = ConfigEntry

    async def get_by_key(self, key: str) -> ConfigEntry | None:
        stmt = select(ConfigEntry).where(ConfigEntry.key == key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_category(self, category: str) -> list[ConfigEntry]:
        stmt = select(ConfigEntry).where(ConfigEntry.category == category)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self, key: str, value: Any, category: str, changed_by: str = "system"
    ) -> ConfigEntry:
        existing = await self.get_by_key(key)
        if existing is not None:
            old_value = existing.value
            existing.value = value
            existing.category = category
            await self._session.flush()
            await self._record_version(key, old_value, value, changed_by)
            await self._session.refresh(existing)
            return existing

        entry = ConfigEntry(key=key, value=value, category=category)
        self._session.add(entry)
        await self._session.flush()
        await self._record_version(key, None, value, changed_by)
        await self._session.refresh(entry)
        return entry

    async def _record_version(
        self, key: str, old_value: Any, new_value: Any, changed_by: str
    ) -> None:
        version = ConfigVersion(
            config_key=key,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
        )
        self._session.add(version)
        await self._session.flush()


class ConfigVersionRepository(BaseRepository[ConfigVersion]):
    model_class = ConfigVersion

    async def get_history(self, key: str, limit: int = 20) -> list[ConfigVersion]:
        stmt = (
            select(ConfigVersion)
            .where(ConfigVersion.config_key == key)
            .order_by(ConfigVersion.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 5: 运行所有测试**

Run: `cd services && python -m pytest tests/config_service/ -v`
Expected: All passed

- [ ] **Step 6: Commit**

```bash
git add services/config_service/models.py services/config_service/repository.py services/tests/config_service/
git commit -m "feat(config): add ConfigEntry/ConfigVersion models and ConfigRepository with upsert + versioning"
```

---

### Task 10: Config Service 业务层 + 路由 + 启动

**Files:**
- Create: `services/config_service/schemas.py`
- Create: `services/config_service/service.py`
- Create: `services/config_service/notifier.py`
- Create: `services/config_service/router.py`
- Create: `services/config_service/main.py`
- Create: `services/tests/config_service/test_router.py`

- [ ] **Step 1: 实现 Schemas**

```python
# services/config_service/schemas.py
from typing import Any
from pydantic import BaseModel, Field


class ConfigRead(BaseModel):
    key: str
    value: Any
    category: str
    description: str | None = None
    model_config = {"from_attributes": True}


class ConfigWrite(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    value: Any
    category: str = "general"
    description: str | None = None


class ConfigVersionRead(BaseModel):
    config_key: str
    old_value: Any | None
    new_value: Any
    changed_by: str
    model_config = {"from_attributes": True}
```

- [ ] **Step 2: 实现 Notifier（观察者模式）**

```python
# services/config_service/notifier.py
import json
from redis.asyncio import Redis


class ConfigNotifier:
    """配置变更通知器。观察者模式——通过 Redis Pub/Sub 广播变更。"""

    CHANNEL = "config:updated"

    def __init__(self, redis: Redis):
        self._redis = redis

    async def notify(self, key: str, value: dict, changed_by: str) -> None:
        message = json.dumps({
            "key": key,
            "value": value,
            "changed_by": changed_by,
        })
        await self._redis.publish(self.CHANNEL, message)
```

- [ ] **Step 3: 实现 Service**

```python
# services/config_service/service.py
from typing import Any

from config_service.repository import ConfigRepository, ConfigVersionRepository
from config_service.notifier import ConfigNotifier
from config_service.schemas import ConfigRead, ConfigVersionRead


class ConfigService:
    """配置业务逻辑。编排仓储和通知器。"""

    def __init__(
        self,
        repo: ConfigRepository,
        version_repo: ConfigVersionRepository,
        notifier: ConfigNotifier | None = None,
    ):
        self._repo = repo
        self._version_repo = version_repo
        self._notifier = notifier

    async def get(self, key: str) -> ConfigRead | None:
        entry = await self._repo.get_by_key(key)
        return ConfigRead.model_validate(entry) if entry else None

    async def get_by_category(self, category: str) -> list[ConfigRead]:
        entries = await self._repo.get_by_category(category)
        return [ConfigRead.model_validate(e) for e in entries]

    async def get_all(self) -> list[ConfigRead]:
        items, _ = await self._repo.list_paginated(page=1, page_size=1000)
        return [ConfigRead.model_validate(e) for e in items]

    async def set(
        self, key: str, value: Any, category: str = "general", changed_by: str = "system"
    ) -> ConfigRead:
        entry = await self._repo.upsert(key, value, category, changed_by)
        if self._notifier:
            await self._notifier.notify(key, value, changed_by)
        return ConfigRead.model_validate(entry)

    async def get_history(self, key: str) -> list[ConfigVersionRead]:
        versions = await self._version_repo.get_history(key)
        return [ConfigVersionRead.model_validate(v) for v in versions]

    async def delete(self, key: str) -> bool:
        entry = await self._repo.get_by_key(key)
        if entry is None:
            return False
        return await self._repo.delete(entry.id)
```

- [ ] **Step 4: 实现 Router**

```python
# services/config_service/router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_schema import ApiResponse
from config_service.schemas import ConfigRead, ConfigWrite
from config_service.service import ConfigService
from config_service.repository import ConfigRepository, ConfigVersionRepository

router = APIRouter(prefix="/config", tags=["config"])


def get_service(session: AsyncSession) -> ConfigService:
    repo = ConfigRepository(session)
    version_repo = ConfigVersionRepository(session)
    return ConfigService(repo, version_repo)


@router.get("/", response_model=ApiResponse)
async def list_configs(
    category: str | None = None,
    session: AsyncSession = Depends(),
):
    service = get_service(session)
    if category:
        items = await service.get_by_category(category)
    else:
        items = await service.get_all()
    return ApiResponse(data=[item.model_dump() for item in items])


@router.get("/{key:path}", response_model=ApiResponse)
async def get_config(key: str, session: AsyncSession = Depends()):
    service = get_service(session)
    entry = await service.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Config '{key}' not found")
    return ApiResponse(data=entry.model_dump())


@router.put("/{key:path}", response_model=ApiResponse)
async def set_config(key: str, body: ConfigWrite, session: AsyncSession = Depends()):
    service = get_service(session)
    entry = await service.set(key, body.value, body.category)
    return ApiResponse(data=entry.model_dump())


@router.delete("/{key:path}", response_model=ApiResponse)
async def delete_config(key: str, session: AsyncSession = Depends()):
    service = get_service(session)
    deleted = await service.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Config '{key}' not found")
    return ApiResponse(message="Deleted")


@router.get("/{key:path}/history", response_model=ApiResponse)
async def get_history(key: str, session: AsyncSession = Depends()):
    service = get_service(session)
    versions = await service.get_history(key)
    return ApiResponse(data=[v.model_dump() for v in versions])
```

- [ ] **Step 5: 实现 main.py**

```python
# services/config_service/main.py
import os
from fastapi import FastAPI
from shared.database import DatabaseManager
from config_service.router import router

app = FastAPI(title="RegFactory Config Service", version="0.1.0")

db = DatabaseManager(
    url=os.getenv("DATABASE_URL", "postgresql+asyncpg://regfactory:regfactory@localhost:5432/regfactory")
)


@app.on_event("startup")
async def startup():
    _ = db.engine


@app.on_event("shutdown")
async def shutdown():
    await db.close()


app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "config_service"}
```

- [ ] **Step 6: 写路由集成测试**

```python
# services/tests/config_service/test_router.py
import pytest
from httpx import AsyncClient, ASGITransport
from shared.base_model import BaseModel
from shared.database import DatabaseManager
from config_service.main import app, db


@pytest.fixture(autouse=True)
async def setup_db():
    test_db = DatabaseManager(url="sqlite+aiosqlite:///")
    async with test_db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    # override app's db for testing
    app.state.db = test_db
    yield
    await test_db.close()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "config_service"
```

- [ ] **Step 7: 运行测试**

Run: `cd services && python -m pytest tests/config_service/test_router.py -v`
Expected: 1 passed

- [ ] **Step 8: Commit**

```bash
git add services/config_service/ services/tests/config_service/
git commit -m "feat(config): add Config Service with schemas, service layer, router, and notifier"
```

---

### Task 11: Alembic 数据库迁移

**Files:**
- Create: `services/migrations/alembic.ini`
- Create: `services/migrations/env.py`

- [ ] **Step 1: 初始化 Alembic**

Run: `cd services && alembic init migrations`

- [ ] **Step 2: 配置 alembic.ini**

修改 `services/migrations/alembic.ini`，设置 `sqlalchemy.url`：
```ini
sqlalchemy.url = postgresql+asyncpg://regfactory:regfactory@localhost:5432/regfactory
```

- [ ] **Step 3: 修改 env.py 支持 async + 导入所有模型**

```python
# services/migrations/env.py（关键部分）
from shared.base_model import BaseModel
from shared.log_models import LogEntry  # 后续 task 创建
from config_service.models import ConfigEntry, ConfigVersion

target_metadata = BaseModel.metadata
```

- [ ] **Step 4: 创建 schema 初始化 SQL**

Run: `cd services && alembic revision -m "create schemas"`

在生成的迁移文件中添加：
```python
def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS config")
    op.execute("CREATE SCHEMA IF NOT EXISTS account")
    op.execute("CREATE SCHEMA IF NOT EXISTS sms")
    op.execute("CREATE SCHEMA IF NOT EXISTS gateway")
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
```

- [ ] **Step 5: 生成表迁移**

Run: `cd services && alembic revision --autogenerate -m "initial tables"`
Run: `cd services && alembic upgrade head`

- [ ] **Step 6: Commit**

```bash
git add services/migrations/
git commit -m "feat(db): add Alembic migrations with schema isolation"
```

---

### Task 12: 全量测试 + 最终验证

- [ ] **Step 1: 运行全部测试**

Run: `cd services && python -m pytest tests/ -v --tb=short`
Expected: All passed

- [ ] **Step 2: 启动 Config Service 验证**

Run: `cd services && uvicorn config_service.main:app --port 8003 --reload`
Run: `curl http://localhost:8003/health`
Expected: `{"status":"ok","service":"config_service"}`

- [ ] **Step 3: 验证 Swagger 文档**

打开浏览器访问 `http://localhost:8003/docs`
Expected: 看到完整的 OpenAPI 文档，包含 /config 路由

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "feat: complete backend foundation - shared library + Config Service"
```
