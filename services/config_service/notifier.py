from collections.abc import Callable
from typing import Any


class ConfigNotifier:
    """进程内配置通知器；单体中无需 Redis Pub/Sub。"""

    def __init__(self):
        self._listeners: list[Callable[[str, dict, str], Any]] = []

    def subscribe(self, listener: Callable[[str, dict, str], Any]) -> None:
        self._listeners.append(listener)

    async def notify(self, key: str, value: dict, changed_by: str) -> None:
        for listener in tuple(self._listeners):
            result = listener(key, value, changed_by)
            if hasattr(result, "__await__"):
                await result
