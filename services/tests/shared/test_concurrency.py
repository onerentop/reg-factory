import pytest
import asyncio
from shared.concurrency import DynamicSemaphore


@pytest.mark.asyncio
async def test_basic_acquire_release():
    sem = DynamicSemaphore(2)
    async with sem:
        assert sem.active == 1
    assert sem.active == 0


@pytest.mark.asyncio
async def test_blocks_at_limit():
    sem = DynamicSemaphore(1)
    acquired = []

    async def worker(name: str):
        async with sem:
            acquired.append(name)
            await asyncio.sleep(0.05)

    t1 = asyncio.create_task(worker("a"))
    await asyncio.sleep(0.01)
    assert sem.active == 1

    t2 = asyncio.create_task(worker("b"))
    await asyncio.sleep(0.01)
    assert sem.waiting == 1

    await asyncio.gather(t1, t2)
    assert sem.active == 0


@pytest.mark.asyncio
async def test_resize_expand():
    sem = DynamicSemaphore(1)
    sem.resize(3)
    assert sem.max_size == 3


@pytest.mark.asyncio
async def test_resize_shrink_no_interrupt():
    sem = DynamicSemaphore(3)
    async with sem:
        sem.resize(1)
        assert sem.max_size == 1
        assert sem.active == 1


@pytest.mark.asyncio
async def test_status():
    sem = DynamicSemaphore(5)
    status = sem.status()
    assert status["max"] == 5
    assert status["active"] == 0
    assert status["waiting"] == 0
