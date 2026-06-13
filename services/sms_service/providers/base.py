from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class OrderStatus(Enum):
    PENDING = "pending"
    RECEIVED = "received"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class AcquireResult:
    order_id: str
    phone_number: str
    provider: str


@dataclass
class CodeResult:
    order_id: str
    code: str | None
    status: OrderStatus


class SMSProvider(ABC):
    """接码平台抽象基类。策略模式——所有平台实现统一接口。"""

    name: str = ""
    display_name: str = ""
    config_schema: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any]):
        self._config = config

    @abstractmethod
    async def get_balance(self) -> float:
        ...

    @abstractmethod
    async def get_number(self, service: str, country: str) -> AcquireResult:
        ...

    @abstractmethod
    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        ...

    @abstractmethod
    async def complete(self, order_id: str) -> None:
        ...

    @abstractmethod
    async def cancel(self, order_id: str) -> None:
        ...

    async def get_services(self) -> list[dict[str, Any]]:
        return []

    async def get_countries(self) -> list[dict[str, Any]]:
        return []

    async def get_prices(self, service: str) -> list[dict[str, Any]]:
        """返回该 service 各国价格/库存：[{country, country_name?, cost, count}]，按 cost 升序。"""
        return []


class ProviderRegistry:
    """适配器注册表。工厂模式——按名称创建 Provider 实例。"""

    _providers: dict[str, type[SMSProvider]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(provider_cls: type[SMSProvider]):
            provider_cls.name = name
            cls._providers[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def get(cls, name: str, config: dict[str, Any]) -> SMSProvider:
        provider_cls = cls._providers.get(name)
        if provider_cls is None:
            raise ValueError(f"Unknown SMS provider: {name}")
        return provider_cls(config)

    @classmethod
    def list_providers(cls) -> list[dict[str, Any]]:
        result = []
        for name, cls_ in cls._providers.items():
            result.append({
                "name": name,
                "display_name": cls_.display_name,
                "config_schema": cls_.config_schema,
            })
        return result

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in cls._providers
