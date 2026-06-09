import pytest
from sqlalchemy import Column, String

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
        await conn.run_sync(FakeEntity.__table__.create, checkfirst=True)
    yield manager
    await manager.close()


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
async def test_update(db):
    async with db.get_session() as session:
        repo = FakeRepository(session)
        entity = await repo.create(name="original")
        eid = entity.id

    async with db.get_session() as session:
        repo = FakeRepository(session)
        updated = await repo.update(eid, name="modified")
        assert updated is not None
        assert updated.name == "modified"


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
