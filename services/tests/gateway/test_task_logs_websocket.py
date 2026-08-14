"""任务日志 WebSocket 的 SQLite 回放和实时推送协议回归。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.registration_jobs import serialize_event_envelope
from gateway.routers import websocket as websocket_router


class FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeDatabase:
    def __init__(self, session=object()):
        self.session = session

    def get_session(self):
        return FakeSessionContext(self.session)


class FakeRuntime:
    terminal_statuses = frozenset({"succeeded", "failed", "cancelled", "interrupted"})

    def __init__(self, subscription=None):
        self.subscription = subscription or asyncio.Queue()
        self.subscriptions = []
        self.unsubscribed = []

    def subscribe(self, task_id):
        self.subscriptions.append(task_id)
        return self.subscription

    def unsubscribe(self, task_id, subscription):
        self.unsubscribed.append((task_id, subscription))


class FakeWebSocket:
    def __init__(self, runtime=None, after="0"):
        self.app = SimpleNamespace(state=SimpleNamespace(task_manager=runtime))
        self.query_params = {"after": after}
        self.accept = AsyncMock()
        self.send_json = AsyncMock()
        self.close = AsyncMock()


def make_job(*, status="running", last_event_seq=0):
    return SimpleNamespace(
        task_id="task-001",
        platform="outlook",
        status=status,
        result=None,
        error_message=None,
        last_event_seq=last_event_seq,
    )


def make_event(seq, event_type="log"):
    return SimpleNamespace(
        task_id="task-001",
        seq=seq,
        event_type=event_type,
        status="running",
        level="INFO",
        message=f"event-{seq}",
        data={"value": seq},
        created_at=None,
    )


@pytest.fixture
def bypass_auth(monkeypatch):
    monkeypatch.setattr(websocket_router, "_authenticate_websocket", AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_task_logs_replays_cursor_then_forwards_live_done(monkeypatch, bypass_auth):
    replayed = make_event(2)
    live_done = {
        "type": "event",
        "task_id": "task-001",
        "seq": 3,
        "data": {"task_id": "task-001", "seq": 3, "event_type": "done"},
    }
    subscription = asyncio.Queue()
    await subscription.put({"type": "event", "task_id": "task-001", "seq": 2, "data": {"event_type": "log"}})
    await subscription.put(live_done)
    runtime = FakeRuntime(subscription)
    websocket = FakeWebSocket(runtime, after="1")
    get_job = AsyncMock(return_value=make_job(last_event_seq=2))
    list_events = AsyncMock(return_value=([replayed], False))

    monkeypatch.setattr("app.core.dependencies.db", FakeDatabase())
    monkeypatch.setattr("gateway.registration_jobs.RegistrationJobService.get_by_task_id", get_job)
    monkeypatch.setattr("gateway.registration_jobs.RegistrationJobService.list_events", list_events)

    await websocket_router.task_logs_websocket(websocket, "task-001")

    assert runtime.subscriptions == ["task-001"]
    assert websocket.send_json.await_args_list == [
        (({"type": "snapshot", "data": {
            "task_id": "task-001",
            "platform": "outlook",
            "status": "running",
            "result": None,
            "error": None,
            "last_event_seq": 2,
        }},),),
        ((serialize_event_envelope(replayed),),),
        ((live_done,),),
        (({"type": "done", "task_id": "task-001", "seq": 3},),),
    ]
    assert runtime.unsubscribed == [("task-001", subscription)]


@pytest.mark.asyncio
async def test_task_logs_terminal_snapshot_replays_before_done(monkeypatch, bypass_auth):
    replayed = make_event(1, "result")
    runtime = FakeRuntime()
    websocket = FakeWebSocket(runtime)

    monkeypatch.setattr("app.core.dependencies.db", FakeDatabase())
    monkeypatch.setattr(
        "gateway.registration_jobs.RegistrationJobService.get_by_task_id",
        AsyncMock(return_value=make_job(status="succeeded", last_event_seq=1)),
    )
    monkeypatch.setattr(
        "gateway.registration_jobs.RegistrationJobService.list_events",
        AsyncMock(return_value=([replayed], False)),
    )

    await websocket_router.task_logs_websocket(websocket, "task-001")

    assert websocket.send_json.await_args_list[-2:] == [
        ((serialize_event_envelope(replayed),),),
        (({"type": "done", "task_id": "task-001", "seq": 1},),),
    ]
    assert runtime.unsubscribed == [("task-001", runtime.subscription)]


@pytest.mark.asyncio
async def test_task_logs_rejects_invalid_cursor_without_subscribing(bypass_auth):
    runtime = FakeRuntime()
    websocket = FakeWebSocket(runtime, after="not-a-sequence")

    await websocket_router.task_logs_websocket(websocket, "task-001")

    websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "after 必须是非负整数"}
    )
    websocket.close.assert_awaited_once_with(code=1008)
    assert runtime.subscriptions == []


@pytest.mark.asyncio
async def test_task_logs_reports_unknown_task_and_unsubscribes(monkeypatch, bypass_auth):
    runtime = FakeRuntime()
    websocket = FakeWebSocket(runtime)

    monkeypatch.setattr("app.core.dependencies.db", FakeDatabase())
    monkeypatch.setattr(
        "gateway.registration_jobs.RegistrationJobService.get_by_task_id",
        AsyncMock(return_value=None),
    )

    await websocket_router.task_logs_websocket(websocket, "missing")

    websocket.send_json.assert_awaited_once_with({"type": "error", "message": "任务不存在"})
    assert runtime.unsubscribed == [("missing", runtime.subscription)]


@pytest.mark.asyncio
async def test_task_logs_reports_missing_runtime(bypass_auth):
    websocket = FakeWebSocket(runtime=None)

    await websocket_router.task_logs_websocket(websocket, "task-001")

    websocket.send_json.assert_awaited_once_with(
        {"type": "error", "message": "本机任务管理器尚未启动"}
    )
    websocket.close.assert_awaited_once_with(code=1011)
