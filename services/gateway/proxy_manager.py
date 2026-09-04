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
    """最少使用优先。usage 可传入外部计数（如 DB 里的累计绑定数）作为初始种子。"""

    def __init__(self, usage: dict[str, int] | None = None):
        self._usage: dict[str, int] = defaultdict(int)
        if usage:
            self._usage.update(usage)

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


class DailyUniqueAllocator(ProxyAllocator):
    """装饰器：先滤掉当天已绑定的代理，再委托内层策略挑选。

    与 DB 无关——调用方负责把「今日已绑定的 proxy id 集合」查出来传进来，
    本类只做过滤与委托，可纯单测。
    """

    def __init__(self, inner: ProxyAllocator, bound_today: set[str]):
        self._inner = inner
        self._bound = bound_today

    def select(self, proxies: list[dict]) -> dict | None:
        return self._inner.select([p for p in proxies if str(p.get("id", "")) not in self._bound])


ALLOCATOR_MAP: dict[str, type[ProxyAllocator]] = {
    "round_robin": RoundRobinAllocator,
    "random": RandomAllocator,
    "least_used": LeastUsedAllocator,
    "region": RegionAllocator,
}


async def check_proxy_health(host: str, port: int, proxy_type: str = "socks5", timeout: float = 10.0, username: str = None, password: str = None) -> str:
    """检测单个代理的健康状态。返回 available / slow / unavailable。"""
    if username and password:
        proxy_url = f"{proxy_type}://{username}:{password}@{host}:{port}"
    else:
        proxy_url = f"{proxy_type}://{host}:{port}"
    test_urls = ["https://www.google.com/generate_204", "https://cp.cloudflare.com", "https://httpbin.org/ip"]
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout, follow_redirects=True) as client:
            for url in test_urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code < 400:
                        elapsed = resp.elapsed.total_seconds() if hasattr(resp, 'elapsed') else 0
                        return "slow" if elapsed > 5 else "available"
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"Proxy {host}:{port} check failed: {e}")
    return "unavailable"


async def detect_proxy_ip(host: str, port: int, proxy_type: str = "socks5", timeout: float = 10.0, username: str = None, password: str = None) -> dict:
    """检测代理出口 IP 和地区。"""
    if username and password:
        proxy_url = f"{proxy_type}://{username}:{password}@{host}:{port}"
    else:
        proxy_url = f"{proxy_type}://{host}:{port}"
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            resp = await client.get("http://ip-api.com/json/?fields=query,country,countryCode,regionName,city")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ip": data.get("query", ""),
                    "region": f"{data.get('countryCode', '')} {data.get('city', '')}".strip(),
                }
    except Exception:
        pass
    return {"ip": "", "region": ""}


async def check_all_proxies(proxies: list[dict]) -> list[dict]:
    """批量检测所有代理。"""
    tasks = []
    for p in proxies:
        tasks.append(check_proxy_health(p["host"], p["port"], p.get("type", "socks5")))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for p, status in zip(proxies, results):
        p["status"] = status if isinstance(status, str) else "unavailable"
    return proxies
