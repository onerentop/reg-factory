"""Shared dependency providers for gateway routers."""
import os

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from shared.database import DatabaseManager
from shared.auth import JwtAuthStrategy
from gateway.repository import (
    UserRepository, ApiKeyRepository, AuditLogRepository,
    AlertRuleRepository, AlertHistoryRepository,
)
from gateway.auth_service import AuthService
from gateway.audit_service import AuditService
from gateway.alert_engine import AlertEngine
from gateway.dashboard_aggregator import DashboardAggregator

db = DatabaseManager(
    url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///regfactory_dev.db")
)

jwt_strategy = JwtAuthStrategy(
    secret=os.getenv("JWT_SECRET_KEY", "dev-secret-change-me"),
)

dashboard = DashboardAggregator(
    account_service_url=os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8002"),
    sms_service_url=os.getenv("SMS_SERVICE_URL", "http://localhost:8001"),
)

_SMS_URL = os.getenv("SMS_SERVICE_URL", "http://localhost:8001")
_ACCOUNT_URL = os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8002")
_CONFIG_URL = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8003")


async def get_session():
    async with db.get_session() as session:
        yield session


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(UserRepository(session), ApiKeyRepository(session), jwt_strategy)


def get_audit_service(session: AsyncSession = Depends(get_session)) -> AuditService:
    return AuditService(AuditLogRepository(session))


def get_alert_engine(session: AsyncSession = Depends(get_session)) -> AlertEngine:
    return AlertEngine(AlertRuleRepository(session), AlertHistoryRepository(session))
