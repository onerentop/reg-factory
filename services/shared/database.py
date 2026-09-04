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
            kwargs = {
                "echo": self._echo,
                "pool_pre_ping": True,
            }
            is_sqlite = "sqlite" in self._url
            if not is_sqlite:
                kwargs["pool_size"] = self._pool_size
            self._engine = create_async_engine(self._url, **kwargs)
            if is_sqlite:
                from sqlalchemy import event

                @event.listens_for(self._engine.sync_engine, "connect")
                def configure_sqlite_connection(dbapi_connection, _connection_record):
                    cursor = dbapi_connection.cursor()
                    try:
                        cursor.execute("PRAGMA journal_mode=WAL")
                        cursor.execute("PRAGMA foreign_keys=ON")
                        cursor.execute("PRAGMA busy_timeout=5000")
                        cursor.execute("PRAGMA synchronous=NORMAL")
                    finally:
                        cursor.close()

            self._session_factory = async_sessionmaker(
                self._engine, expire_on_commit=False
            )
        return self._engine

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        _ = self.engine
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
