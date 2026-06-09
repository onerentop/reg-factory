"""Microsoft Graph API 客户端。从 common/mailbox.py 迁移核心 OAuth2 + 邮件读取逻辑。"""

import httpx
import logging

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
DEFAULT_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
DEFAULT_SCOPE = "https://graph.microsoft.com/.default offline_access"


class GraphClient:
    """Microsoft Graph API 客户端。负责 token 刷新和邮件读取。"""

    def __init__(self, client_id: str = DEFAULT_CLIENT_ID):
        self._client_id = client_id

    async def get_access_token(self, refresh_token: str) -> str | None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": self._client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": DEFAULT_SCOPE,
            })
            if resp.status_code == 200:
                return resp.json().get("access_token")
            logger.warning(f"Token refresh failed: {resp.status_code}")
            return None

    async def fetch_messages(
        self, access_token: str, folder: str = "inbox", top: int = 10
    ) -> list[dict]:
        url = f"{GRAPH_API_BASE}/me/mailFolders/{folder}/messages"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={
                "Authorization": f"Bearer {access_token}",
            }, params={"$top": str(top), "$orderby": "receivedDateTime desc"})
            if resp.status_code == 200:
                return resp.json().get("value", [])
            logger.warning(f"Fetch messages failed: {resp.status_code}")
            return []

    async def fetch_from_folders(
        self, access_token: str, folders: list[str] | None = None, top: int = 10
    ) -> list[dict]:
        if folders is None:
            folders = ["inbox", "junkemail"]
        messages = []
        for folder in folders:
            msgs = await self.fetch_messages(access_token, folder, top)
            messages.extend(msgs)
        return messages
