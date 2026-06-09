import asyncio
import httpx

from sms_service.providers.base import (
    SMSProvider,
    ProviderRegistry,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


@ProviderRegistry.register("sms_bower")
class SmsBowerProvider(SMSProvider):
    display_name = "SmsBower"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://smsbower.com/api",
        },
    }

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", "https://smsbower.com/api")

    @property
    def _api_key(self) -> str:
        return self._config.get("api_key", "")

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                json=data,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_balance(self) -> float:
        result = await self._request("GET", "/balance")
        return float(result.get("balance", 0))

    async def get_number(self, service: str, country: str) -> AcquireResult:
        result = await self._request("POST", "/activations", {
            "service": service,
            "country": country,
        })
        if "id" not in result:
            raise ValueError(f"Failed to get number: {result}")
        return AcquireResult(
            order_id=str(result["id"]),
            phone_number=result.get("phone", ""),
            provider=self.name,
        )

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            result = await self._request("GET", f"/activations/{order_id}")
            status = result.get("status", "")
            if status == "completed" and result.get("code"):
                return CodeResult(
                    order_id=order_id,
                    code=result["code"],
                    status=OrderStatus.RECEIVED,
                )
            if status == "cancelled":
                return CodeResult(order_id=order_id, code=None, status=OrderStatus.CANCELLED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        await self._request("PUT", f"/activations/{order_id}", {"status": "completed"})

    async def cancel(self, order_id: str) -> None:
        await self._request("PUT", f"/activations/{order_id}", {"status": "cancelled"})
