from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AuthResult:
    """认证结果值对象。"""
    authenticated: bool
    user_id: str = ""
    role: str = ""
    scopes: list[str] = field(default_factory=list)
    error: str = ""


class AuthStrategy(ABC):
    """认证策略接口。所有认证方式实现此接口。"""

    @abstractmethod
    def verify(self, credential: str) -> AuthResult:
        ...
