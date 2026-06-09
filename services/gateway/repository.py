import uuid
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_repository import BaseRepository
from gateway.models import User, ApiKey, AuditLog, AlertRule, AlertHistory


class UserRepository(BaseRepository[User]):
    model_class = User

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class ApiKeyRepository(BaseRepository[ApiKey]):
    model_class = ApiKey

    async def get_by_key(self, key: str) -> ApiKey | None:
        stmt = select(ApiKey).where(and_(ApiKey.key == key, ApiKey.is_active == True))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_owner(self, owner_id: str) -> list[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.owner_id == owner_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def increment_usage(self, key_id: uuid.UUID) -> None:
        key = await self.get_by_id(key_id)
        if key:
            from datetime import datetime, timezone
            key.call_count += 1
            key.last_used_at = datetime.now(timezone.utc)
            await self._session.flush()


class AuditLogRepository(BaseRepository[AuditLog]):
    model_class = AuditLog

    async def list_filtered(
        self, operator: str | None = None, action: str | None = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple[list[AuditLog], int]:
        conditions = []
        if operator:
            conditions.append(AuditLog.operator == operator)
        if action:
            conditions.append(AuditLog.action == action)
        where = and_(*conditions) if conditions else True

        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(AuditLog).where(where)
        total = (await self._session.execute(count_stmt)).scalar_one()

        items_stmt = (
            select(AuditLog).where(where)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
        result = await self._session.execute(items_stmt)
        return list(result.scalars().all()), total


class AlertRuleRepository(BaseRepository[AlertRule]):
    model_class = AlertRule

    async def get_enabled(self) -> list[AlertRule]:
        stmt = select(AlertRule).where(AlertRule.enabled == True)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AlertHistoryRepository(BaseRepository[AlertHistory]):
    model_class = AlertHistory
