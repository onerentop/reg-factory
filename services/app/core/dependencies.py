"""单体应用共享的 FastAPI 依赖和基础设施实例。"""
from typing import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from gateway.auth_service import AuthService
from gateway.repository import UserRepository
from shared.auth import JwtAuthStrategy
from shared.database import DatabaseManager

settings = get_settings()
db = DatabaseManager(url=settings.database_url)
jwt_strategy = JwtAuthStrategy(secret=settings.jwt_secret_key)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with db.get_session() as session:
        yield session


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(UserRepository(session), jwt_strategy)

