import asyncio
from typing import Any

from shared.concurrency import DynamicSemaphore
from shared.browser_providers import (
    BrowserProvider, ProfileHandle, ProxyConfig, FingerprintConfig,
    PlaywrightProvider,
)


class BrowserPool:
    """浏览器实例池。对象池模式——管理浏览器实例的借出与归还。"""

    def __init__(self, provider: BrowserProvider | None = None, max_size: int = 8):
        self._provider = provider or PlaywrightProvider()
        self._semaphore = DynamicSemaphore(max_size)
        self._active_profiles: dict[str, ProfileHandle] = {}

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def active_count(self) -> int:
        return len(self._active_profiles)

    @property
    def max_size(self) -> int:
        return self._semaphore.max_size

    def resize(self, new_max: int) -> None:
        self._semaphore.resize(new_max)

    def switch_provider(self, provider: BrowserProvider) -> None:
        self._provider = provider

    async def acquire(
        self, proxy: ProxyConfig | None = None, fingerprint: FingerprintConfig | None = None
    ) -> ProfileHandle:
        await self._semaphore.__aenter__()
        profile = await self._provider.create_profile(proxy, fingerprint)
        self._active_profiles[profile.profile_id] = profile
        return profile

    async def release(self, profile: ProfileHandle) -> None:
        await self._provider.close_browser(profile)
        await self._provider.delete_profile(profile)
        self._active_profiles.pop(profile.profile_id, None)
        await self._semaphore.__aexit__(None, None, None)

    def status(self) -> dict:
        return {
            "provider": self._provider.name,
            "max_size": self._semaphore.max_size,
            "active": self.active_count,
            "available": self._semaphore.max_size - self._semaphore.active,
        }
