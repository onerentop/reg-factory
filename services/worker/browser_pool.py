import asyncio
from dataclasses import dataclass
from typing import Any
from abc import ABC, abstractmethod

from shared.concurrency import DynamicSemaphore


@dataclass
class ProxyConfig:
    type: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def to_url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.type}://{auth}{self.host}:{self.port}"


@dataclass
class FingerprintConfig:
    user_agent: str | None = None
    language: str | None = None
    timezone: str | None = None
    resolution: tuple[int, int] | None = None


@dataclass
class ProfileHandle:
    provider: str
    profile_id: str
    ws_endpoint: str
    metadata: dict[str, Any] | None = None


class BrowserProvider(ABC):
    """指纹浏览器抽象基类。策略模式——不同浏览器实现统一接口。"""

    name: str = ""

    @abstractmethod
    async def create_profile(self, proxy: ProxyConfig | None = None, fingerprint: FingerprintConfig | None = None) -> ProfileHandle:
        ...

    @abstractmethod
    async def open_browser(self, profile: ProfileHandle) -> Any:
        ...

    @abstractmethod
    async def close_browser(self, profile: ProfileHandle) -> None:
        ...

    @abstractmethod
    async def delete_profile(self, profile: ProfileHandle) -> None:
        ...

    def supports_stealth(self) -> bool:
        return False


class PlaywrightProvider(BrowserProvider):
    """原生 Playwright 降级兜底方案。"""

    name = "playwright"

    async def create_profile(self, proxy: ProxyConfig | None = None, fingerprint: FingerprintConfig | None = None) -> ProfileHandle:
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

    def supports_stealth(self) -> bool:
        return False


class BrowserPool:
    """浏览器实例池。对象池模式——管理浏览器实例的借出与归还。"""

    def __init__(self, provider: BrowserProvider, max_size: int = 8):
        self._provider = provider
        self._semaphore = DynamicSemaphore(max_size)
        self._active_profiles: dict[str, ProfileHandle] = {}

    @property
    def active_count(self) -> int:
        return len(self._active_profiles)

    @property
    def max_size(self) -> int:
        return self._semaphore.max_size

    def resize(self, new_max: int) -> None:
        self._semaphore.resize(new_max)

    async def acquire(self, proxy: ProxyConfig | None = None, fingerprint: FingerprintConfig | None = None) -> ProfileHandle:
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
