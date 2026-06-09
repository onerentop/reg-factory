import asyncio
import httpx
import logging
from typing import Any

from shared.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ResilientHttpClient:
    """带熔断和限流的 HTTP 客户端。

    每个目标服务一个 CircuitBreaker 实例。
    Semaphore 控制并发上限。
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_concurrent: int = 20,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._breakers: dict[str, CircuitBreaker] = {}
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._client: httpx.AsyncClient | None = None

    def _get_breaker(self, base_url: str) -> CircuitBreaker:
        if base_url not in self._breakers:
            self._breakers[base_url] = CircuitBreaker(
                failure_threshold=self._failure_threshold,
                recovery_timeout=self._recovery_timeout,
            )
        return self._breakers[base_url]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        base = url.split("/")[0] + "//" + url.split("/")[2] if "/" in url else url
        breaker = self._get_breaker(base)

        if not breaker.allow_request():
            raise ConnectionError(f"Circuit breaker OPEN for {base}")

        async with self._semaphore:
            client = await self._get_client()
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                breaker.record_success()
                return response
            except Exception as e:
                breaker.record_failure()
                logger.warning(f"Request failed: {method} {url} - {e}")
                raise

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
