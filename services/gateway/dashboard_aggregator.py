from typing import Any
from shared.http_client import ResilientHttpClient


class DashboardAggregator:
    """仪表盘数据聚合器。使用 ResilientHttpClient（带熔断）。"""

    def __init__(
        self,
        account_service_url: str = "http://localhost:8002",
        sms_service_url: str = "http://localhost:8001",
    ):
        self._account_url = account_service_url
        self._sms_url = sms_service_url
        self._client = ResilientHttpClient(timeout=10, failure_threshold=3, recovery_timeout=15)

    async def get_dashboard_data(self) -> dict[str, Any]:
        account_stats = await self._fetch_account_stats()
        sms_stats = await self._fetch_sms_stats()
        return {"accounts": account_stats, "sms": sms_stats}

    async def _fetch_account_stats(self) -> dict:
        try:
            resp = await self._client.get(f"{self._account_url}/accounts", params={"page_size": "1"})
            data = resp.json().get("data", {})
            return {"total": data.get("total", 0)}
        except Exception:
            return {"total": 0, "error": "Account service unavailable"}

    async def _fetch_sms_stats(self) -> dict:
        try:
            resp = await self._client.get(f"{self._sms_url}/sms/providers")
            providers = resp.json().get("data", [])
            return {"providers_count": len(providers)}
        except Exception:
            return {"providers_count": 0, "error": "SMS service unavailable"}

    async def close(self) -> None:
        await self._client.close()
