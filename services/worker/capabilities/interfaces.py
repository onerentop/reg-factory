"""共享能力服务接口（Strategy/Adapter）。具体实现在后续里程碑随平台迁移逐个落地。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class BrowserSession:
    """一次浏览器会话的值对象。"""
    page: Any
    context: Any
    profile_id: str
    proxy: str


@dataclass
class EmailAccount:
    """邮箱账号值对象。"""
    email: str
    password: str
    refresh_token: str | None = None
    client_id: str | None = None
    cookies: list | None = None


class BrowserService(ABC):
    """浏览器会话能力。session() 是 async 上下文管理器——会话在 with 块内存活，退出自动清理。"""
    @abstractmethod
    def session(self, *, proxy: str, idx: int = 0):
        """返回 async 上下文管理器，yield 一个 BrowserSession。"""
        ...


class ProxyService(ABC):
    @abstractmethod
    def acquire(self) -> str: ...
    @abstractmethod
    def report(self, proxy: str, *, ok: bool) -> None: ...


class CaptchaService(ABC):
    """单一解法（Strategy）。子类设 kind 标识挑战类型。"""
    kind: str = ""
    @abstractmethod
    async def solve(self, page: Any, context: dict) -> bool: ...


class CaptchaResolver:
    """Registry：挑战类型 -> 解法。Outlook 需先 perimeterx 再 arkose，由 flow 步骤依次调用。"""

    def __init__(self):
        self._solvers: dict[str, CaptchaService] = {}

    def register(self, solver: CaptchaService) -> None:
        self._solvers[solver.kind] = solver

    async def solve(self, kind: str, page: Any, context: dict) -> bool:
        return await self._solvers[kind].solve(page, context)


class EmailPoolService(ABC):
    @abstractmethod
    def acquire(self) -> EmailAccount | None: ...
    @abstractmethod
    def add(self, account: EmailAccount) -> None: ...


class SmsService(ABC):
    @abstractmethod
    async def get_number(self, *, country: str) -> str: ...
    @abstractmethod
    async def get_code(self, number: str) -> str: ...
    @abstractmethod
    async def release(self, number: str) -> None: ...


class TokenExtractor(ABC):
    @abstractmethod
    async def extract(self, page: Any, account: EmailAccount) -> dict: ...
