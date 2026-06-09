import httpx
from typing import Any

from shared.browser_providers.base import (
    BrowserProvider, ProfileHandle, ProxyConfig, FingerprintConfig,
)


class IXBrowserProvider(BrowserProvider):
    """ixBrowser 指纹浏览器适配器。通过本地 REST API 管理 profile。"""

    name = "ixbrowser"

    def __init__(self, api_url: str = "http://127.0.0.1:53200"):
        self._api_url = api_url

    def supports_stealth(self) -> bool:
        return True

    async def create_profile(
        self, proxy: ProxyConfig | None = None, fingerprint: FingerprintConfig | None = None
    ) -> ProfileHandle:
        payload: dict[str, Any] = {"name": "reg-factory-auto"}
        if proxy:
            payload["proxy"] = {
                "type": proxy.type,
                "host": proxy.host,
                "port": proxy.port,
                "username": proxy.username or "",
                "password": proxy.password or "",
            }
        if fingerprint:
            if fingerprint.user_agent:
                payload["user_agent"] = fingerprint.user_agent
            if fingerprint.language:
                payload["language"] = fingerprint.language
            if fingerprint.timezone:
                payload["timezone"] = fingerprint.timezone
            if fingerprint.resolution:
                payload["resolution"] = f"{fingerprint.resolution[0]}x{fingerprint.resolution[1]}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._api_url}/api/profile/create", json=payload)
            resp.raise_for_status()
            data = resp.json().get("data", {})

        return ProfileHandle(
            provider=self.name,
            profile_id=str(data.get("id", "")),
            ws_endpoint="",
            metadata=data,
        )

    async def open_browser(self, profile: ProfileHandle) -> Any:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._api_url}/api/profile/open",
                json={"id": profile.profile_id},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            profile.ws_endpoint = data.get("ws", "")
            return data

    async def close_browser(self, profile: ProfileHandle) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{self._api_url}/api/profile/close",
                json={"id": profile.profile_id},
            )

    async def delete_profile(self, profile: ProfileHandle) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{self._api_url}/api/profile/delete",
                json={"id": profile.profile_id},
            )
