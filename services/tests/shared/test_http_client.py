import pytest
from shared.http_client import ResilientHttpClient


def test_client_init():
    client = ResilientHttpClient(timeout=10, max_concurrent=5)
    assert client._timeout == 10


@pytest.mark.asyncio
async def test_circuit_breaker_created_per_host():
    client = ResilientHttpClient()
    b1 = client._get_breaker("http://localhost:8001")
    b2 = client._get_breaker("http://localhost:8002")
    b3 = client._get_breaker("http://localhost:8001")
    assert b1 is not b2
    assert b1 is b3


@pytest.mark.asyncio
async def test_close():
    client = ResilientHttpClient()
    await client.close()
    assert client._client is None
