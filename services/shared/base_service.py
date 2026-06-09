import os
import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from shared.database import DatabaseManager
from shared.log_handler import setup_logger


class BaseService:
    """微服务基类。模板方法模式——标准化服务启动流程。

    子类通过继承获得：数据库连接、日志、CORS、健康检查、trace_id 传播。
    """

    def __init__(self, name: str, port: int, db_schema: str | None = None):
        self._name = name
        self._port = port
        self._db_schema = db_schema
        self._db: DatabaseManager | None = None
        self._logger = setup_logger(name)

    @property
    def db(self) -> DatabaseManager:
        if self._db is None:
            self._db = DatabaseManager(
                url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///regfactory_dev.db")
            )
        return self._db

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def create_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self._logger.info(f"{self._name} starting on port {self._port}")
            _ = self.db.engine
            yield
            await self.db.close()
            self._logger.info(f"{self._name} stopped")

        app = FastAPI(
            title=f"RegFactory {self._name}",
            version="0.1.0",
            lifespan=lifespan,
        )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.middleware("http")
        async def trace_id_middleware(request: Request, call_next: Callable) -> Response:
            import uuid
            trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4())[:8])
            request.state.trace_id = trace_id
            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id
            return response

        @app.get("/health")
        async def health():
            return {"status": "ok", "service": self._name}

        app.state.db = self.db
        app.state.service_name = self._name

        return app

    async def get_session(self):
        async with self.db.get_session() as session:
            yield session
