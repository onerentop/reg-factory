"""本机任务实时推送与持久化回放的协议不变量。"""

import asyncio
from types import SimpleNamespace

import pytest

from gateway.registration_jobs import serialize_event_envelope
from worker.local_task_manager import LocalProcessTaskManager


def _event(seq: int, event_type: str) -> dict:
    return {
        "type": "event",
        "task_id": "task-001",
        "seq": seq,
        "data": {"task_id": "task-001", "seq": seq, "event_type": event_type},
    }


def test_event_envelope_has_the_same_shape_for_live_and_replay():
    persisted = SimpleNamespace(
        task_id="task-001",
        seq=7,
        event_type="log",
        status="running",
        level="INFO",
        message="browser opened",
        data={"source_sequence": 1},
        created_at=None,
    )

    envelope = serialize_event_envelope(persisted)

    assert envelope == {
        "type": "event",
        "task_id": "task-001",
        "seq": 7,
        "data": {
            "task_id": "task-001",
            "seq": 7,
            "event_type": "log",
            "status": "running",
            "level": "INFO",
            "message": "browser opened",
            "data": {"source_sequence": 1},
            "created_at": None,
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["result", "failed", "done", "interrupted"])
async def test_full_subscription_retains_terminal_event(event_type: str):
    manager = LocalProcessTaskManager()
    subscription: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
    manager._subscribers["task-001"].add(subscription)
    try:
        await manager._broadcast("task-001", _event(1, "log"))
        await manager._broadcast("task-001", _event(2, event_type))

        assert subscription.get_nowait()["data"]["event_type"] == event_type
    finally:
        manager._event_queue.close()


@pytest.mark.asyncio
async def test_full_subscription_does_not_evict_existing_terminal_event():
    manager = LocalProcessTaskManager()
    subscription: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
    manager._subscribers["task-001"].add(subscription)
    try:
        await manager._broadcast("task-001", _event(1, "result"))
        await manager._broadcast("task-001", _event(2, "done"))

        assert subscription.get_nowait()["data"]["event_type"] == "result"
    finally:
        manager._event_queue.close()


@pytest.mark.asyncio
async def test_full_subscription_may_drop_nonterminal_log_event():
    manager = LocalProcessTaskManager()
    subscription: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
    manager._subscribers["task-001"].add(subscription)
    try:
        first = _event(1, "log")
        await manager._broadcast("task-001", first)
        await manager._broadcast("task-001", _event(2, "log"))

        assert subscription.get_nowait() is first
    finally:
        manager._event_queue.close()
