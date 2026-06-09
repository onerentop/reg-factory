import pytest
from worker.browser_pool import (
    BrowserPool, PlaywrightProvider, ProxyConfig, FingerprintConfig, ProfileHandle,
)


@pytest.fixture
def pool():
    provider = PlaywrightProvider()
    return BrowserPool(provider=provider, max_size=3)


@pytest.mark.asyncio
async def test_acquire_and_release(pool):
    profile = await pool.acquire()
    assert profile.provider == "playwright"
    assert pool.active_count == 1
    await pool.release(profile)
    assert pool.active_count == 0


@pytest.mark.asyncio
async def test_pool_status(pool):
    status = pool.status()
    assert status["max_size"] == 3
    assert status["active"] == 0
    assert status["provider"] == "playwright"


@pytest.mark.asyncio
async def test_pool_resize(pool):
    pool.resize(5)
    assert pool.max_size == 5


@pytest.mark.asyncio
async def test_proxy_config_to_url():
    proxy = ProxyConfig(type="socks5", host="1.2.3.4", port=1080, username="u", password="p")
    assert proxy.to_url() == "socks5://u:p@1.2.3.4:1080"

    proxy2 = ProxyConfig(type="http", host="5.6.7.8", port=8080)
    assert proxy2.to_url() == "http://5.6.7.8:8080"
