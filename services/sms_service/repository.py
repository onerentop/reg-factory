from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_repository import BaseRepository
from sms_service.models import SmsOrder, SmsPlatformConfig


class SmsOrderRepository(BaseRepository[SmsOrder]):
    model_class = SmsOrder


class SmsPlatformConfigRepository(BaseRepository[SmsPlatformConfig]):
    model_class = SmsPlatformConfig

    async def get_by_provider(self, provider_name: str) -> SmsPlatformConfig | None:
        stmt = select(SmsPlatformConfig).where(
            SmsPlatformConfig.provider_name == provider_name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_enabled_ordered(self) -> list[SmsPlatformConfig]:
        stmt = (
            select(SmsPlatformConfig)
            .where(SmsPlatformConfig.enabled == "true")
            .order_by(SmsPlatformConfig.priority.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
