"""firefox.fun 接码平台适配器。你的主用平台，从 common/sms.py 迁移。
API: act=getPhone/getPhoneCode/cancelPhone, 管道分隔响应。
"""

import asyncio
import httpx

from sms_service.providers.base import (
    SMSProvider, ProviderRegistry, AcquireResult, CodeResult, OrderStatus,
)


@ProviderRegistry.register("firefox_fun")
class FirefoxFunProvider(SMSProvider):
    display_name = "Firefox.fun"
    config_schema = {
        "token": {"type": "string", "label": "API Token", "required": True},
        "base_url": {"type": "string", "label": "API Base URL", "default": "http://www.firefox.fun/yhapi.ashx"},
        "project_id": {"type": "string", "label": "项目号 (iid)", "required": True, "default": "2313"},
        "max_price": {"type": "string", "label": "价格上限", "default": "0"},
    }

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", "http://www.firefox.fun/yhapi.ashx")

    @property
    def _token(self) -> str:
        return self._config.get("token", "")

    async def get_balance(self) -> float:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._base_url, params={"act": "getBalance", "token": self._token})
            try:
                return float(resp.text.strip())
            except ValueError:
                return 0.0

    async def get_number(self, service: str, country: str) -> AcquireResult:
        project_id = service or self._config.get("project_id", "2313")
        max_price = self._config.get("max_price", "0")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._base_url, params={
                "act": "getPhone", "token": self._token, "iid": project_id,
                "country": country, "maxPrice": str(max_price),
                "did": "", "dock": "", "otpmode": "", "mobile": "", "pushUrl": "",
            })
        text = resp.text.strip()
        parts = text.split("|")
        if parts[0] == "1" and len(parts) >= 8:
            pkey, country_code, phone = parts[1], parts[4], parts[7]
            return AcquireResult(order_id=pkey, phone_number=f"+{country_code}{phone}", provider=self.name)
        raise ValueError(f"firefox.fun get_number failed: {text}")

    async def get_code(self, order_id: str, timeout: int = 180) -> CodeResult:
        elapsed = 0
        while elapsed < timeout:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self._base_url, params={
                    "act": "getPhoneCode", "token": self._token, "pkey": order_id,
                })
            parts = resp.text.strip().split("|")
            if parts[0] == "1" and len(parts) >= 2:
                return CodeResult(order_id=order_id, code=parts[1], status=OrderStatus.RECEIVED)
            await asyncio.sleep(5)
            elapsed += 5
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        pass

    async def cancel(self, order_id: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(self._base_url, params={
                "act": "cancelPhone", "token": self._token, "pkey": order_id,
            })
