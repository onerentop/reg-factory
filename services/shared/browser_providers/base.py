from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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
    metadata: dict[str, Any] = field(default_factory=dict)


class BrowserProvider(ABC):
    """指纹浏览器抽象基类。策略模式。"""

    name: str = ""

    @abstractmethod
    async def create_profile(
        self, proxy: ProxyConfig | None = None, fingerprint: FingerprintConfig | None = None
    ) -> ProfileHandle: ...

    @abstractmethod
    async def open_browser(self, profile: ProfileHandle) -> Any: ...

    @abstractmethod
    async def close_browser(self, profile: ProfileHandle) -> None: ...

    @abstractmethod
    async def delete_profile(self, profile: ProfileHandle) -> None: ...

    def supports_stealth(self) -> bool:
        return False

    def supports_proxy_binding(self) -> bool:
        return True
