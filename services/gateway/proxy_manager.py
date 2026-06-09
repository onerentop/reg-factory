import asyncio
import random
import logging
from abc import ABC, abstractmethod
from typing import Any
from collections import defaultdict

import httpx

logger = logging.getLogger(__name__)


class ProxyAllocator(ABC):
    """代理分配策略抽象基类。策略模式。"""

    @abstractmethod
    def select(self, proxies: list[dict]) -> dict | None:
        ...


class RoundRobinAllocator(ProxyAllocator):
    """轮询分配。"""

    def __init__(self):
        self._index = 0

    def select(self, proxies: list[dict]) -> dict | None:
        if not proxies:
            return None
        proxy = proxies[self._index % len(proxies)]
        self._index += 1
        return proxy


class RandomAllocator(ProxyAllocator):
    """随机分配。"""

    def select(self, proxies: list[dict]) -> dict | None:
        return random.choice(proxies) if proxies else None


class LeastUsedAllocator(ProxyAllocator):
    """最少使用优先。"""

    def __init__(self):
        self._usage: dict[str, int] = defaultdict(int)

    def select(self, proxies: list[dict]) -> dict | None:
        if not proxies:
            return None
        proxy = min(proxies, key=lambda p: self._usage.get(p.get("id", ""), 0))
        self._usage[proxy.get("id", "")] += 1
        return proxy


class RegionAllocator(ProxyAllocator):
    """按地区分配。"""

    def __init__(self, target_region: str = ""):
        self._target = target_region
        self._fallback = RandomAllocator()

    def select(self, proxies: list[dict]) -> dict | None:
        if self._target:
            regional = [p for p in proxies if p.get("region", "").upper() == self._target.upper()]
            if regional:
                return random.choice(regional)
        return self._fallback.select(proxies)


ALLOCATOR_MAP: dict[str, type[ProxyAllocator]] = {
    "round_robin": RoundRobinAllocator,
    "random": RandomAllocator,
    "least_used": LeastUsedAllocator,
    "region": RegionAllocator,
}


async def check_proxy_health(host: str, port: int, proxy_type: str = "socks5", timeout: float = 5.0) -> str:
    """检测单个代理的健康状态。返回 available / slow / unavailable。"""
    proxy_url = f"{proxy_type}://{host}:{port}"
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            resp = await client.get("https://httpbin.org/ip")
            if resp.status_code == 200:
                elapsed = resp.elapsed.total_seconds() if hasattr(resp, 'elapsed') else 0
                return "slow" if elapsed > 3 else "available"
    except Exception as e:
        logger.debug(f"Proxy {host}:{port} check failed: {e}")
    return "unavailable"


async def check_all_proxies(proxies: list[dict]) -> list[dict]:
    """批量检测所有代理。"""
    tasks = []
    for p in proxies:
        tasks.append(check_proxy_health(p["host"], p["port"], p.get("type", "socks5")))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for p, status in zip(proxies, results):
        p["status"] = status if isinstance(status, str) else "unavailable"
    return proxies
