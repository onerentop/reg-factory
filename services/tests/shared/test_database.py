import pytest
from shared.database import DatabaseManager


@pytest.fixture
def db_manager():
    return DatabaseManager(url="sqlite+aiosqlite:///")


@pytest.mark.asyncio
async def test_create_engine(db_manager):
    engine = db_manager.engine
    assert engine is not None
    assert "sqlite" in str(engine.url)


@pytest.mark.asyncio
async def test_session_context_manager(db_manager):
    async with db_manager.get_session() as session:
        assert session is not None
        assert session.is_active


@pytest.mark.asyncio
async def test_engine_singleton(db_manager):
    engine1 = db_manager.engine
    engine2 = db_manager.engine
    assert engine1 is engine2


@pytest.mark.asyncio
async def test_close(db_manager):
    _ = db_manager.engine
    await db_manager.close()
    assert db_manager._engine is None
