"""Graph Token 批量提取。从 extract_graph_tokens.py 迁移核心 OAuth2 流程。"""

import httpx
import logging

logger = logging.getLogger(__name__)

TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


class GraphTokenExtractor:
    """通过 OAuth2 密码授权从 Outlook 账号提取 refresh_token。"""

    def __init__(self, client_id: str = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"):
        self._client_id = client_id

    async def extract(self, email: str, password: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": self._client_id,
                "grant_type": "password",
                "username": email,
                "password": password,
                "scope": "https://graph.microsoft.com/.default offline_access",
            })
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "email": email,
                    "access_token": data.get("access_token", ""),
                    "refresh_token": data.get("refresh_token", ""),
                }
            return {
                "success": False,
                "email": email,
                "error": resp.json().get("error_description", f"HTTP {resp.status_code}"),
            }

    async def extract_batch(self, accounts: list[dict]) -> list[dict]:
        results = []
        for acct in accounts:
            result = await self.extract(acct["email"], acct["password"])
            results.append(result)
            logger.info(f"Token extract {acct['email']}: {'ok' if result['success'] else result.get('error', '')[:50]}")
        return results
