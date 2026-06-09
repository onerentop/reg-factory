import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AuditRecorder:
    """审计记录器。收集审计事件供后续持久化。"""

    def __init__(self):
        self._records: list[dict[str, Any]] = []
        self._callbacks: list[Callable] = []

    def add_callback(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    def record(
        self,
        operator: str,
        action: str,
        target: str | None = None,
        before: Any = None,
        after: Any = None,
    ) -> None:
        entry = {
            "operator": operator,
            "action": action,
            "target": target,
            "before_value": before,
            "after_value": after,
        }
        self._records.append(entry)
        for cb in self._callbacks:
            try:
                cb(entry)
            except Exception:
                pass
        logger.info(f"Audit: {operator} {action} {target or ''}")

    @property
    def records(self) -> list[dict[str, Any]]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()


def audited(action: str, target_param: str | None = None):
    """审计装饰器。装饰器模式——为方法自动记录审计日志。

    Usage:
        @audited("delete_account", target_param="account_id")
        async def delete(self, account_id: str): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            target = kwargs.get(target_param, "") if target_param else ""
            logger.info(f"Audit[{action}]: target={target}")
            result = await func(*args, **kwargs)
            return result
        return wrapper
    return decorator
