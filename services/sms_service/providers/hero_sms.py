from typing import Any

import httpx

from sms_service.providers.base import ProviderRegistry
from sms_service.providers.sms_activate_base import SmsActivateProvider


@ProviderRegistry.register("hero_sms")
class HeroSmsProvider(SmsActivateProvider):
    display_name = "HeroSMS"
    _default_base_url = "https://hero-sms.com/stubs/handler_api.php"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://hero-sms.com/stubs/handler_api.php",
        },
    }

    @property
    def _v1_base_url(self) -> str:
        # handler_api 与 v1 是不同 base：.../stubs/handler_api.php → .../api/v1
        return self._base_url.replace("/stubs/handler_api.php", "/api/v1")

    async def get_offers(self, service: str, country: str) -> dict[str, Any]:
        """HeroSMS v1 GET /activations/offers：返回该国某服务的价位阶梯 + 价格/库存。
        鉴权用 header `Authorization: ApiKey <key>`（与 handler_api 的 query api_key 不同）。"""
        async with httpx.AsyncClient(
            timeout=30, headers={"Authorization": f"ApiKey {self._api_key}"}
        ) as client:
            resp = await client.get(
                f"{self._v1_base_url}/activations/offers",
                params={"services": service, "countries": str(country)},
            )
            resp.raise_for_status()
            body = resp.json()
        node = ((body.get("data") or {}).get(service) or {}).get(str(country)) or {}
        price_map = node.get("map") or {}
        tiers = [{"price": float(p), "count": int(c)} for p, c in price_map.items()]
        tiers.sort(key=lambda t: t["price"])
        return {
            "prices": node.get("prices") or {},
            "counts": node.get("counts") or {},
            "tiers": tiers,
        }
