import asyncio
import httpx

from sms_service.providers.base import (
    SMSProvider,
    ProviderRegistry,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


@ProviderRegistry.register("sms_pool")
class SmsPoolProvider(SMSProvider):
    display_name = "SMSPool"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://api.smspool.net",
        },
    }

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", "https://api.smspool.net")

    @property
    def _api_key(self) -> str:
        return self._config.get("api_key", "")

    async def _post(self, path: str, data: dict | None = None) -> dict:
        form = {"key": self._api_key}
        if data:
            form.update(data)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._base_url}{path}", data=form)
            resp.raise_for_status()
            return resp.json()

    async def get_balance(self) -> float:
        result = await self._post("/request/balance")
        return float(result.get("balance", 0))

    async def get_number(self, service: str, country: str) -> AcquireResult:
        result = await self._post("/purchase/sms", {
            "service": service,
            "country": country,
        })
        if "order_id" not in result:
            raise ValueError(f"Failed to get number: {result}")
        return AcquireResult(
            order_id=str(result["order_id"]),
            phone_number=result.get("phonenumber", result.get("number", "")),
            provider=self.name,
        )

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            result = await self._post("/sms/check", {"orderid": order_id})
            status = result.get("status", 0)
            if status == 3:
                sms = result.get("sms", "")
                return CodeResult(order_id=order_id, code=sms, status=OrderStatus.RECEIVED)
            if status == 6:
                return CodeResult(order_id=order_id, code=None, status=OrderStatus.CANCELLED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        await self._post("/sms/activate", {"orderid": order_id})

    async def cancel(self, order_id: str) -> None:
        await self._post("/sms/cancel", {"orderid": order_id})
