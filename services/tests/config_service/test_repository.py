import pytest
from shared.database import DatabaseManager
from shared.base_model import BaseModel
from config_service.models import ConfigEntry, ConfigVersion
from config_service.repository import ConfigRepository, ConfigVersionRepository


@pytest.fixture
async def db():
    manager = DatabaseManager(url="sqlite+aiosqlite:///")
    async with manager.engine.begin() as conn:
        await conn.run_sync(ConfigEntry.__table__.create, checkfirst=True)
        await conn.run_sync(ConfigVersion.__table__.create, checkfirst=True)
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


@pytest.mark.asyncio
async def test_version_history(db):
    async with db.get_session() as session:
        repo = ConfigRepository(session)
        await repo.upsert("v.key", {"v": 1}, "test", "user1")

    async with db.get_session() as session:
        repo = ConfigRepository(session)
        await repo.upsert("v.key", {"v": 2}, "test", "user2")

    async with db.get_session() as session:
        version_repo = ConfigVersionRepository(session)
        history = await version_repo.get_history("v.key")
        assert len(history) >= 2
