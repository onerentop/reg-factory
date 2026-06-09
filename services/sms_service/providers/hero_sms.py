import asyncio
import httpx

from sms_service.providers.base import (
    SMSProvider,
    ProviderRegistry,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


@ProviderRegistry.register("hero_sms")
class HeroSmsProvider(SMSProvider):
    display_name = "HeroSMS"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://hero-sms.com/stubs/handler_api.php",
        },
    }

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", "https://hero-sms.com/stubs/handler_api.php")

    @property
    def _api_key(self) -> str:
        return self._config.get("api_key", "")

    async def _request(self, params: dict) -> str:
        params["api_key"] = self._api_key
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._base_url, params=params)
            resp.raise_for_status()
            return resp.text

    async def get_balance(self) -> float:
        text = await self._request({"action": "getBalance"})
        if "ACCESS_BALANCE" in text:
            return float(text.split(":")[1])
        raise ValueError(f"Failed to get balance: {text}")

    async def get_number(self, service: str, country: str) -> AcquireResult:
        text = await self._request({
            "action": "getNumber",
            "service": service,
            "country": country,
        })
        if "ACCESS_NUMBER" not in text:
            raise ValueError(f"Failed to get number: {text}")
        parts = text.split(":")
        activation_id = parts[1]
        phone = parts[2]
        return AcquireResult(
            order_id=activation_id,
            phone_number=phone,
            provider=self.name,
        )

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            text = await self._request({
                "action": "getStatus",
                "id": order_id,
            })
            if text.startswith("STATUS_OK"):
                code = text.split(":")[1]
                return CodeResult(order_id=order_id, code=code, status=OrderStatus.RECEIVED)
            if text == "STATUS_CANCEL":
                return CodeResult(order_id=order_id, code=None, status=OrderStatus.CANCELLED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        await self._request({"action": "setStatus", "id": order_id, "status": "6"})

    async def cancel(self, order_id: str) -> None:
        await self._request({"action": "setStatus", "id": order_id, "status": "8"})
