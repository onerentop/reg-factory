import asyncio
import json
from typing import Any

import httpx

from sms_service.providers.base import (
    SMSProvider,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


class SmsActivateProvider(SMSProvider):
    """SMS-Activate handler_api.php 协议基类（模板方法）。
    GET {base_url}?api_key=X&action=Y → 'ACCESS_*'/'STATUS_*' 纯文本。
    子类只需声明 display_name / _default_base_url / config_schema。"""

    _default_base_url: str = ""

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", self._default_base_url)

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
        if text.startswith("ACCESS_BALANCE"):
            return float(text.split(":")[1])
        raise ValueError(f"{self.name} getBalance failed: {text}")

    async def get_number(self, service: str, country: str, max_price: str = "0", fixed_price: bool = False) -> AcquireResult:
        params = {"action": "getNumber", "service": service, "country": country}
        if max_price and str(max_price) not in ("0", "0.0", ""):
            params["maxPrice"] = str(max_price)
            if fixed_price:
                params["fixedPrice"] = "true"
        text = await self._request(params)
        if not text.startswith("ACCESS_NUMBER"):
            raise ValueError(f"{self.name} getNumber failed: {text}")
        parts = text.split(":")
        return AcquireResult(order_id=parts[1], phone_number=parts[2], provider=self.name)

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            text = await self._request({"action": "getStatus", "id": order_id})
            if text.startswith("STATUS_OK"):
                return CodeResult(order_id=order_id, code=text.split(":")[1], status=OrderStatus.RECEIVED)
            if text == "STATUS_CANCEL":
                return CodeResult(order_id=order_id, code=None, status=OrderStatus.CANCELLED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        await self._request({"action": "setStatus", "id": order_id, "status": "6"})

    async def cancel(self, order_id: str) -> None:
        await self._request({"action": "setStatus", "id": order_id, "status": "8"})

    async def get_prices(self, service: str) -> list[dict[str, Any]]:
        text = await self._request({"action": "getPrices", "service": service})
        data = json.loads(text) if text.strip().startswith("{") else {}
        rows = []
        for cid, svc in data.items():
            info = svc.get(service) if isinstance(svc, dict) else None
            if info and "cost" in info:
                rows.append({"country": str(cid), "cost": float(info["cost"]), "count": int(info.get("count", 0))})
        rows.sort(key=lambda r: r["cost"])
        return rows
