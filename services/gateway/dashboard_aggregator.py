from typing import Any
import httpx


class DashboardAggregator:
    """仪表盘数据聚合器。从各微服务收集数据组装统一视图。"""

    def __init__(
        self,
        account_service_url: str = "http://localhost:8002",
        sms_service_url: str = "http://localhost:8001",
    ):
        self._account_url = account_service_url
        self._sms_url = sms_service_url

    async def get_dashboard_data(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            account_stats = await self._fetch_account_stats(client)
            sms_stats = await self._fetch_sms_stats(client)

        return {
            "accounts": account_stats,
            "sms": sms_stats,
        }

    async def _fetch_account_stats(self, client: httpx.AsyncClient) -> dict:
        try:
            resp = await client.get(f"{self._account_url}/accounts", params={"page_size": 1})
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return {"total": data.get("total", 0)}
        except Exception:
            pass
        return {"total": 0, "error": "Account service unavailable"}

    async def _fetch_sms_stats(self, client: httpx.AsyncClient) -> dict:
        try:
            resp = await client.get(f"{self._sms_url}/sms/providers")
            if resp.status_code == 200:
                providers = resp.json().get("data", [])
                return {"providers_count": len(providers)}
        except Exception:
            pass
        return {"providers_count": 0, "error": "SMS service unavailable"}
