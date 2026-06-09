from typing import Any

from config_service.repository import ConfigRepository, ConfigVersionRepository
from config_service.notifier import ConfigNotifier
from config_service.schemas import ConfigRead, ConfigVersionRead


class ConfigService:
    """配置业务逻辑。编排仓储和通知器。"""

    def __init__(
        self,
        repo: ConfigRepository,
        version_repo: ConfigVersionRepository,
        notifier: ConfigNotifier | None = None,
    ):
        self._repo = repo
        self._version_repo = version_repo
        self._notifier = notifier

    async def get(self, key: str) -> ConfigRead | None:
        entry = await self._repo.get_by_key(key)
        return ConfigRead.model_validate(entry) if entry else None

    async def get_by_category(self, category: str) -> list[ConfigRead]:
        entries = await self._repo.get_by_category(category)
        return [ConfigRead.model_validate(e) for e in entries]

    async def get_all(self) -> list[ConfigRead]:
        items, _ = await self._repo.list_paginated(page=1, page_size=1000)
        return [ConfigRead.model_validate(e) for e in items]

    async def set(
        self, key: str, value: Any, category: str = "general", changed_by: str = "system"
    ) -> ConfigRead:
        entry = await self._repo.upsert(key, value, category, changed_by)
        if self._notifier:
            await self._notifier.notify(key, value, changed_by)
        return ConfigRead.model_validate(entry)

    async def get_history(self, key: str) -> list[ConfigVersionRead]:
        versions = await self._version_repo.get_history(key)
        return [ConfigVersionRead.model_validate(v) for v in versions]

    async def delete(self, key: str) -> bool:
        entry = await self._repo.get_by_key(key)
        if entry is None:
            return False
        return await self._repo.delete(entry.id)
