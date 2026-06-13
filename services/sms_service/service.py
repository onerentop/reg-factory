from typing import Any

from sms_service.providers.base import (
    SMSProvider,
    ProviderRegistry,
    AcquireResult,
    CodeResult,
    OrderStatus,
)
from sms_service.repository import SmsOrderRepository, SmsPlatformConfigRepository
from sms_service.schemas import (
    ProviderInfo,
    BalanceResponse,
    PlatformConfigRead,
)


class SmsService:
    """SMS 业务逻辑。编排 Provider 和 Repository。"""

    def __init__(
        self,
        order_repo: SmsOrderRepository,
        config_repo: SmsPlatformConfigRepository,
    ):
        self._order_repo = order_repo
        self._config_repo = config_repo

    def list_providers(self) -> list[ProviderInfo]:
        return [
            ProviderInfo(**p) for p in ProviderRegistry.list_providers()
        ]

    async def _get_provider(self, provider_name: str) -> SMSProvider:
        platform = await self._config_repo.get_by_provider(provider_name)
        if platform is None:
            raise ValueError(f"Platform '{provider_name}' not configured")
        if platform.enabled != "true":
            raise ValueError(f"Platform '{provider_name}' is disabled")
        return ProviderRegistry.get(provider_name, platform.config)

    async def get_balance(self, provider_name: str) -> BalanceResponse:
        provider = await self._get_provider(provider_name)
        balance = await provider.get_balance()
        return BalanceResponse(provider=provider_name, balance=balance)

    async def get_prices(self, provider_name: str, service: str) -> list:
        provider = await self._get_provider(provider_name)
        return await provider.get_prices(service)

    async def acquire_number(
        self, service: str, country: str, provider_name: str | None = None,
        max_price: str = "0", fixed_price: bool = False,
    ) -> AcquireResult:
        if provider_name:
            provider = await self._get_provider(provider_name)
        else:
            provider = await self._select_best_provider()

        result = await provider.get_number(service, country, max_price=max_price, fixed_price=fixed_price)
        await self._order_repo.create(
            provider=provider.name,
            service=service,
            country=country,
            phone_number=result.phone_number,
            order_id_external=result.order_id,
            status=OrderStatus.PENDING,
        )
        return result

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        order = await self._find_order(order_id)
        provider = await self._get_provider(order.provider)
        result = await provider.get_code(order_id, timeout)

        if result.code:
            await self._order_repo.update(
                order.id, code=result.code, status=OrderStatus.RECEIVED
            )
        return result

    async def complete(self, order_id: str) -> None:
        order = await self._find_order(order_id)
        provider = await self._get_provider(order.provider)
        await provider.complete(order_id)
        await self._order_repo.update(order.id, status=OrderStatus.COMPLETED)

    async def cancel(self, order_id: str) -> None:
        order = await self._find_order(order_id)
        provider = await self._get_provider(order.provider)
        await provider.cancel(order_id)
        await self._order_repo.update(order.id, status=OrderStatus.CANCELLED)

    async def get_platform_configs(self) -> list[PlatformConfigRead]:
        configs = await self._config_repo.get_enabled_ordered()
        return [PlatformConfigRead.model_validate(c) for c in configs]

    async def save_platform_config(
        self, provider_name: str, display_name: str, enabled: str,
        priority: float, config: dict
    ) -> PlatformConfigRead:
        existing = await self._config_repo.get_by_provider(provider_name)
        if existing:
            updated = await self._config_repo.update(
                existing.id,
                display_name=display_name,
                enabled=enabled,
                priority=priority,
                config=config,
            )
            return PlatformConfigRead.model_validate(updated)
        else:
            created = await self._config_repo.create(
                provider_name=provider_name,
                display_name=display_name,
                enabled=enabled,
                priority=priority,
                config=config,
            )
            return PlatformConfigRead.model_validate(created)

    async def _select_best_provider(self) -> SMSProvider:
        platforms = await self._config_repo.get_enabled_ordered()
        if not platforms:
            raise ValueError("No enabled SMS platforms")
        return ProviderRegistry.get(platforms[0].provider_name, platforms[0].config)

    async def _find_order(self, external_order_id: str) -> Any:
        from sqlalchemy import select
        from sms_service.models import SmsOrder
        stmt = select(SmsOrder).where(
            SmsOrder.order_id_external == external_order_id
        )
        result = await self._order_repo._session.execute(stmt)
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order '{external_order_id}' not found")
        return order
