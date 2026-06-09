import json
import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ConfigClient:
    """配置热更新客户端。观察者模式——订阅 Redis 配置变更通知。"""

    def __init__(self, config_service_url: str = "http://localhost:8003"):
        self._config_url = config_service_url
        self._cache: dict[str, Any] = {}
        self._listeners: dict[str, list[Callable]] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return dict(self._cache)

    def set_local(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def on_change(self, key: str, callback: Callable) -> None:
        self._listeners.setdefault(key, []).append(callback)

    def on_any_change(self, callback: Callable) -> None:
        self._listeners.setdefault("*", []).append(callback)

    async def load_from_service(self) -> None:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self._config_url}/config/")
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    for item in data:
                        self._cache[item["key"]] = item["value"]
                    logger.info(f"Loaded {len(data)} config entries from Config Service")
        except Exception as e:
            logger.warning(f"Failed to load config from service: {e}")

    async def start_watching(self, redis_url: str = "redis://localhost:6379/0") -> None:
        import redis.asyncio as aioredis
        try:
            r = aioredis.from_url(redis_url)
            pubsub = r.pubsub()
            await pubsub.subscribe("config:updated")
            logger.info("Subscribed to config:updated channel")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await self._handle_update(message["data"])
        except Exception as e:
            logger.error(f"Config watcher error: {e}")

    async def _handle_update(self, raw_data: bytes) -> None:
        try:
            data = json.loads(raw_data)
            key = data.get("key", "")
            value = data.get("value")
            old_value = self._cache.get(key)
            self._cache[key] = value
            for cb in self._listeners.get(key, []):
                cb(key, value, old_value)
            for cb in self._listeners.get("*", []):
                cb(key, value, old_value)
            logger.info(f"Config updated: {key}")
        except Exception as e:
            logger.error(f"Failed to handle config update: {e}")
