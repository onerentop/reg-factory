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
        """GET {base_url}{path}，header 带 apiKey；校验信封 code==0 后返回 data。"""
        async with httpx.AsyncClient(
            timeout=30, headers={"apiKey": self._api_key}
        ) as client:
            resp = await client.get(f"{self._base_url}{path}", params=params or {})
            resp.raise_for_status()
            body = resp.json()
        if body.get("code") != 0:
            raise ValueError(f"SMS Cloud {body.get('code')}: {body.get('message')}")
        return body.get("data") or {}

    async def get_balance(self) -> float:
        data = await self._get("/public/sms/balance")
        return float(data.get("balance", 0))

    async def get_number(self, service: str, country: str) -> AcquireResult:
        data = await self._get("/public/sms/getNumber", {
            "serviceCode": service,
            "countryCode": country,
        })
        return AcquireResult(
            order_id=str(data["id"]),
            phone_number=data["phoneNumber"],
            provider=self.name,
        )

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            data = await self._get(f"/public/sms/orders/sync/{order_id}")
            code = data.get("code")
            if code:
                return CodeResult(order_id=order_id, code=code, status=OrderStatus.RECEIVED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        await self._get("/complete", {"order_id": order_id})

    async def cancel(self, order_id: str) -> None:
        await self._get("/cancel", {"order_id": order_id})
