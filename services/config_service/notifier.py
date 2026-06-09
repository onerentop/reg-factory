import json
from redis.asyncio import Redis


class ConfigNotifier:
    """配置变更通知器。观察者模式——通过 Redis Pub/Sub 广播变更。"""

    CHANNEL = "config:updated"

    def __init__(self, redis: Redis):
        self._redis = redis

    async def notify(self, key: str, value: dict, changed_by: str) -> None:
        message = json.dumps({
            "key": key,
            "value": value,
            "changed_by": changed_by,
        })
        await self._redis.publish(self.CHANNEL, message)
