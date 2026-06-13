"""sms_service 路由行为测试 fixture：TestClient + dependency_overrides + fake service。

TestClient(app) 不加 with → 不触发 lifespan(无 create_all/DB 网络)；
路由依赖经 app.dependency_overrides 换 fake，故不碰真 DB/服务。
"""
import pytest
from fastapi.testclient import TestClient

from sms_service.main import app, get_service
from sms_service.schemas import BalanceResponse, PlatformConfigRead
from sms_service.providers.base import AcquireResult, CodeResult, OrderStatus


def _make_config(**kwargs) -> PlatformConfigRead:
    defaults = dict(
        provider_name="smsactivate",
        display_name="SMS Activate",
        enabled="true",
        priority=1.0,
        config={"api_key": "test"},
    )
    defaults.update(kwargs)
    return PlatformConfigRead(**defaults)


class FakeSmsService:
    async def get_balance(self, provider_name: str) -> BalanceResponse:
        if provider_name == "smsactivate":
            return BalanceResponse(provider=provider_name, balance=99.5)
        raise ValueError(f"Platform '{provider_name}' not configured")

    async def acquire_number(self, service: str, country: str, provider: str | None = None, max_price: str = "0", fixed_price: bool = False) -> AcquireResult:
        if provider == "badprovider":
            raise ValueError("No enabled SMS platforms")
        return AcquireResult(order_id="order-001", phone_number="+79001234567", provider="smsactivate")

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        if order_id == "missing-order":
            raise ValueError(f"Order '{order_id}' not found")
        return CodeResult(order_id=order_id, code="123456", status=OrderStatus.RECEIVED)

    async def complete(self, order_id: str) -> None:
        if order_id == "missing-order":
            raise ValueError(f"Order '{order_id}' not found")

    async def cancel(self, order_id: str) -> None:
        if order_id == "missing-order":
            raise ValueError(f"Order '{order_id}' not found")

    async def get_platform_configs(self) -> list[PlatformConfigRead]:
        return [_make_config()]

    async def save_platform_config(
        self, provider_name: str, display_name: str, enabled: str,
        priority: float, config: dict
    ) -> PlatformConfigRead:
        return _make_config(
            provider_name=provider_name,
            display_name=display_name,
            enabled=enabled,
            priority=priority,
            config=config,
        )


@pytest.fixture
def fake_service():
    return FakeSmsService()


@pytest.fixture
def client(fake_service):
    app.dependency_overrides[get_service] = lambda: fake_service
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
