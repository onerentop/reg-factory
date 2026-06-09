import asyncio
import httpx

from sms_service.providers.base import (
    SMSProvider,
    ProviderRegistry,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


@ProviderRegistry.register("sms_cloud")
class SmsCloudProvider(SMSProvider):
    display_name = "SMS Cloud"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://smscloud.sbs/api/system",
        },
    }

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", "https://smscloud.sbs/api/system")

    @property
    def _api_key(self) -> str:
        return self._config.get("api_key", "")

    async def _get(self, path: str, params: dict | None = None) -> dict:
        all_params = {"api_key": self._api_key}
        if params:
            all_params.update(params)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self._base_url}{path}", params=all_params)
            resp.raise_for_status()
            return resp.json()

    async def get_balance(self) -> float:
        result = await self._get("/get_balance")
        return float(result.get("balance", 0))

    async def get_number(self, service: str, country: str) -> AcquireResult:
        result = await self._get("/get_number", {
            "service_code": service,
            "country": country,
        })
        if "phone" not in result:
            raise ValueError(f"Failed to get number: {result}")
        return AcquireResult(
            order_id=str(result.get("order_id", result.get("id", ""))),
            phone_number=result["phone"],
            provider=self.name,
        )

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            result = await self._get("/get_code", {"order_id": order_id})
            code = result.get("code")
            if code:
                return CodeResult(order_id=order_id, code=code, status=OrderStatus.RECEIVED)
            status = result.get("status", "")
            if status == "cancelled":
                return CodeResult(order_id=order_id, code=None, status=OrderStatus.CANCELLED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        await self._get("/complete", {"order_id": order_id})

    async def cancel(self, order_id: str) -> None:
        await self._get("/cancel", {"order_id": order_id})
