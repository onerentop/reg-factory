import pytest
from sms_service.providers.base import (
    SMSProvider,
    ProviderRegistry,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


@ProviderRegistry.register("test_provider")
class TestProvider(SMSProvider):
    display_name = "Test Provider"
    config_schema = {"api_key": {"type": "string", "label": "API Key"}}

    async def get_balance(self) -> float:
        return 99.99

    async def get_number(self, service: str, country: str) -> AcquireResult:
        return AcquireResult(order_id="test-123", phone_number="+1234567890", provider="test_provider")

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        return CodeResult(order_id=order_id, code="123456", status=OrderStatus.RECEIVED)

    async def complete(self, order_id: str) -> None:
        pass

    async def cancel(self, order_id: str) -> None:
        pass


def test_register_provider():
    assert ProviderRegistry.is_registered("test_provider")


def test_list_providers():
    providers = ProviderRegistry.list_providers()
    names = [p["name"] for p in providers]
    assert "test_provider" in names


def test_get_provider():
    provider = ProviderRegistry.get("test_provider", {"api_key": "test"})
    assert isinstance(provider, TestProvider)
    assert provider._config == {"api_key": "test"}


def test_get_unknown_provider():
    with pytest.raises(ValueError, match="Unknown SMS provider"):
        ProviderRegistry.get("nonexistent", {})


@pytest.mark.asyncio
async def test_provider_get_balance():
    provider = ProviderRegistry.get("test_provider", {})
    balance = await provider.get_balance()
    assert balance == 99.99


@pytest.mark.asyncio
async def test_provider_get_number():
    provider = ProviderRegistry.get("test_provider", {})
    result = await provider.get_number("google", "US")
    assert result.phone_number == "+1234567890"
    assert result.provider == "test_provider"


@pytest.mark.asyncio
async def test_provider_get_code():
    provider = ProviderRegistry.get("test_provider", {})
    result = await provider.get_code("test-123")
    assert result.code == "123456"
    assert result.status == OrderStatus.RECEIVED
