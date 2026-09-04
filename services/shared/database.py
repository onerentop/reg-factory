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
                    # 关掉驱动的隐式 BEGIN，改由下面的 "begin" 事件显式发。缺了这一步，
                    # 连接始终处于 autocommit：SAVEPOINT 一 RELEASE 就落盘，外层
                    # session.rollback() 无事可撤。实测症状——ProxyBindingService.claim()
                    # 在 begin_nested() 里插的 binding，回滚后仍留在库里，
                    # 于是 gateway 注册流程中途抛异常时会漏出无主 binding，
                    # 启动扫描按 Job 反查扫不到它，那个 IP 白白锁到本地零点。
                    # 别把这行「简化」掉，它和下面的 sqlite_explicit_begin 是一对。
                    dbapi_connection.isolation_level = None
                    cursor = dbapi_connection.cursor()
                    try:
                        cursor.execute("PRAGMA journal_mode=WAL")
                        cursor.execute("PRAGMA foreign_keys=ON")
                        cursor.execute("PRAGMA busy_timeout=5000")
                        cursor.execute("PRAGMA synchronous=NORMAL")
                    finally:
                        cursor.close()

                @event.listens_for(self._engine.sync_engine, "begin")
                def sqlite_explicit_begin(conn):
                    # SQLAlchemy 官方「接管 SQLite 事务控制」配方的另一半：
                    # 隐式 BEGIN 被上面关掉后，必须在这里补一条真正的 BEGIN，
                    # 否则所有写入都是自动提交，事务/SAVEPOINT 语义整体失效。
                    conn.exec_driver_sql("BEGIN")

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
