import asyncio
import httpx
from typing import Any

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

    async def _get(self, path: str, params: dict | None = None) -> Any:
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

    async def get_number(self, service: str, country: str, max_price: str = "0", fixed_price: bool = False) -> AcquireResult:
        # smscloud getNumber 不支持价格过滤（价格在 inventory 层）；max_price/fixed_price 仅为签名兼容
        data = await self._get("/public/sms/getNumber", {"serviceCode": service, "countryCode": country})
        return AcquireResult(order_id=str(data["id"]), phone_number=data["phoneNumber"], provider=self.name)

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
        await self._get(f"/public/sms/orders/finish/{order_id}")

    async def cancel(self, order_id: str) -> None:
        await self._get(f"/public/sms/orders/cancel/{order_id}")

    async def get_prices(self, service: str) -> list[dict[str, Any]]:
        # getInventory 返回 data 列表（_get 已解信封）；retailPrice=零售价，count=库存
        data = await self._get("/public/sms/getInventory", {"serviceCode": service})
        rows = data if isinstance(data, list) else []
        out = [{
            "country": str(r["country"]),
            "country_name": r.get("countryName", ""),
            "cost": float(r.get("retailPrice", 0)),
            "count": int(r.get("count", 0)),
        } for r in rows if "country" in r]
        out.sort(key=lambda r: r["cost"])
        return out
