"""ChatGPT2API 上传器。从 export_chatgpt2api.py 迁移核心 POST 逻辑。"""

import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ChatGpt2ApiUploader:
    """将 ChatGPT 网页号导入 chatgpt2api 接口。"""

    def __init__(self, host: str, api_key: str):
        self._host = host.rstrip("/")
        self._key = api_key

    async def upload_accounts(self, accounts: list[dict[str, Any]]) -> dict:
        if not self._host or not self._key:
            return {"success": False, "error": "chatgpt2api not configured"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._host}/api/accounts",
                json=accounts,
                headers={"Authorization": f"Bearer {self._key}"},
            )
            if resp.status_code < 400:
                return {"success": True, "count": len(accounts)}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

    async def upload_single(self, account: dict[str, Any]) -> dict:
        return await self.upload_accounts([account])
