import json
from typing import Any

from sms_service.providers.base import ProviderRegistry
from sms_service.providers.sms_activate_base import SmsActivateProvider


@ProviderRegistry.register("sms_bower")
class SmsBowerProvider(SmsActivateProvider):
    display_name = "SmsBower"
    _default_base_url = "https://smsbower.com/stubs/handler_api.php"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://smsbower.com/stubs/handler_api.php",
        },
    }

    async def get_offers(self, service: str, country: str) -> dict[str, Any]:
        """SmsBower getPricesV2：{国家:{服务:{价格:数量}}} → 价位阶梯 + 价格/库存。
        与 hero 的 /activations/offers 等价（hero 走 v1，smsbower 走 handler_api getPricesV2）。"""
        text = await self._request({"action": "getPricesV2", "service": service, "country": str(country)})
        data = json.loads(text) if text.strip().startswith("{") else {}
        node = (data.get(str(country)) or {}).get(service) or {}
        tiers = []
        for p, c in node.items():
            try:
                tiers.append({"price": float(p), "count": int(c)})
            except (ValueError, TypeError):
                continue
        tiers.sort(key=lambda t: t["price"])
        total = sum(t["count"] for t in tiers)
        return {
            "prices": {"min": tiers[0]["price"] if tiers else 0},
            "counts": {"total": total, "physical": total},
            "tiers": tiers,
        }
