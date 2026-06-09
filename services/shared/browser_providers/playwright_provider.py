import asyncio
from typing import Any

from shared.browser_providers.base import (
    BrowserProvider, ProfileHandle, ProxyConfig, FingerprintConfig,
)


class PlaywrightProvider(BrowserProvider):
    """原生 Playwright 降级兜底。不带指纹隔离。"""

    name = "playwright"

    async def create_profile(
        self, proxy: ProxyConfig | None = None, fingerprint: FingerprintConfig | None = None
    ) -> ProfileHandle:
        profile_id = f"pw_{id(self)}_{asyncio.get_event_loop().time()}"
        return ProfileHandle(
            provider=self.name,
            profile_id=profile_id,
            ws_endpoint="",
            metadata={"proxy": proxy, "fingerprint": fingerprint},
        )

    async def open_browser(self, profile: ProfileHandle) -> Any:
        return None

    async def close_browser(self, profile: ProfileHandle) -> None:
        pass

    async def delete_profile(self, profile: ProfileHandle) -> None:
        pass
