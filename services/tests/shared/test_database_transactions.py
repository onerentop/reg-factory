"""数据库层的事务语义保证。

pysqlite/aiosqlite 默认自己管 BEGIN：不显式接管的话连接一直处于 autocommit，
SAVEPOINT 一 RELEASE 就落盘，外层 session.rollback() 撤不掉任何东西。
DatabaseManager 用 connect(isolation_level=None) + begin(BEGIN) 两个监听器接管了
事务控制，这里把行为钉死，防止有人把那两个监听器当冗余删掉。
"""
import pytest
from sqlalchemy import Column, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError

from shared.base_model import BaseModel
from shared.database import DatabaseManager


class SavepointProbe(BaseModel):
    """与业务域无关的探针表，只为验证事务边界。"""

    __tablename__ = "savepoint_probe"
    __table_args__ = (UniqueConstraint("name", name="uq_savepoint_probe_name"),)

    name = Column(String(50), nullable=False)


@pytest.fixture
async def db(tmp_path):
    # 必须落到真实文件：内存库掩盖不了问题，但文件库才和生产同构。
    manager = DatabaseManager(url=f"sqlite+aiosqlite:///{tmp_path / 'probe.db'}")
    async with manager.engine.begin() as conn:
        await conn.run_sync(SavepointProbe.__table__.create, checkfirst=True)
    yield manager
    await manager.close()


async def _count(manager: DatabaseManager) -> int:
    assert manager._session_factory is not None
    async with manager._session_factory() as session:
        result = await session.execute(select(func.count(SavepointProbe.id)))
        return int(result.scalar() or 0)


@pytest.mark.asyncio
async def test_rollback_undoes_savepoint_write(db):
    """begin_nested() 里的写入，必须能被外层 rollback() 撤销。

    回归的症状：ProxyBindingService.claim() 在 SAVEPOINT 里插的 binding
    在回滚后依然留在库里，于是注册流程中途失败会漏出无主 binding，
    该代理当天的额度直到本地零点都收不回来。
    """
    assert db._session_factory is not None
    async with db._session_factory() as session:
        async with session.begin_nested():
            session.add(SavepointProbe(name="rolled-back"))
        await session.rollback()

    assert await _count(db) == 0


@pytest.mark.asyncio
async def test_commit_persists_savepoint_write(db):
    """反向保证：接管事务控制之后，正常提交路径依然落盘。"""
    assert db._session_factory is not None
    async with db._session_factory() as session:
        async with session.begin_nested():
            session.add(SavepointProbe(name="committed"))
        await session.commit()

    assert await _count(db) == 1


@pytest.mark.asyncio
async def test_savepoint_isolates_integrity_error(db):
    """SAVEPOINT 撞唯一约束后，外层事务仍可继续写——抢占重试循环靠这条活着。"""
    assert db._session_factory is not None
    async with db._session_factory() as session:
        async with session.begin_nested():
            session.add(SavepointProbe(name="dup"))

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(SavepointProbe(name="dup"))

        async with session.begin_nested():
            session.add(SavepointProbe(name="other"))
        await session.commit()

    assert await _count(db) == 2
