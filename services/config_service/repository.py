from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_repository import BaseRepository
from config_service.models import ConfigEntry, ConfigVersion


class ConfigRepository(BaseRepository[ConfigEntry]):
    model_class = ConfigEntry

    async def get_by_key(self, key: str) -> ConfigEntry | None:
        stmt = select(ConfigEntry).where(ConfigEntry.key == key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_category(self, category: str) -> list[ConfigEntry]:
        stmt = select(ConfigEntry).where(ConfigEntry.category == category)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self, key: str, value: Any, category: str, changed_by: str = "system"
    ) -> ConfigEntry:
        existing = await self.get_by_key(key)
        if existing is not None:
            old_value = existing.value
            existing.value = value
            existing.category = category
            await self._session.flush()
            await self._record_version(key, old_value, value, changed_by)
            await self._session.refresh(existing)
            return existing

        entry = ConfigEntry(key=key, value=value, category=category)
        self._session.add(entry)
        await self._session.flush()
        await self._record_version(key, None, value, changed_by)
        await self._session.refresh(entry)
        return entry

    async def _record_version(
        self, key: str, old_value: Any, new_value: Any, changed_by: str
    ) -> None:
        version = ConfigVersion(
            config_key=key,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
        )
        self._session.add(version)
        await self._session.flush()


class ConfigVersionRepository(BaseRepository[ConfigVersion]):
    model_class = ConfigVersion

    async def get_history(self, key: str, limit: int = 20) -> list[ConfigVersion]:
        stmt = (
            select(ConfigVersion)
            .where(ConfigVersion.config_key == key)
            .order_by(ConfigVersion.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
