"""单体注册 API：只验证本机任务投递与 SQLite 状态查询，不执行浏览器流程。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from gateway.deps import get_session
from gateway.main import app


@pytest.fixture(autouse=True)
def no_database_session():
    app.dependency_overrides[get_session] = lambda: None
    with patch("gateway.registration_jobs.RegistrationJobService.enqueue", new=AsyncMock()), patch(
        "gateway.registration_jobs.RegistrationJobService.get_by_task_id",
        new=AsyncMock(return_value=None),
    ):
        yield
    app.dependency_overrides.pop(get_session, None)


class FakeRuntime:
    def __init__(self):
        self.submissions = []

    async def submit_registration(self, task_id, **kwargs):
        self.submissions.append((task_id, kwargs))


def test_register_outlook_queues_local_task(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    with patch(
        "gateway.routers.registration._pick_active_proxy",
        new_callable=AsyncMock,
        return_value="socks5://1.2.3.4:1080",
    ):
        response = client.post("/register/outlook", json={"config": {"headless": True}})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert data["count"] == 1
    assert len(data["task_ids"]) == 1
    task_id, call = runtime.submissions[0]
    assert task_id == data["task_ids"][0]
    assert call["platform"] == "outlook"
    assert call["config"]["mode"] == "browser"


def test_register_multiple_tasks_use_same_proxy(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    with patch(
        "gateway.routers.registration._pick_active_proxy",
        new_callable=AsyncMock,
        return_value="socks5://source:1080",
    ):
        response = client.post("/register/outlook", json={"count": 2})

    assert response.status_code == 200
    assert len(runtime.submissions) == 2
    assert [call[1]["proxy"] for call in runtime.submissions] == [
        "socks5://source:1080",
        "socks5://source:1080",
    ]


def test_register_uses_proxy_id_without_exposing_password(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    proxy_id = str(uuid.uuid4())
    with patch(
        "gateway.routers.registration._resolve_proxy",
        new_callable=AsyncMock,
        return_value="socks5://user:secret@9.9.9.9:1080",
    ) as resolve_proxy:
        response = client.post("/register/outlook", json={"proxy_id": proxy_id})

    assert response.status_code == 200
    resolve_proxy.assert_awaited_once_with(None, proxy_id, "")
    assert runtime.submissions[0][1]["proxy"] == "socks5://user:secret@9.9.9.9:1080"


def test_register_uses_provided_proxy_and_mode(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    with patch(
        "gateway.routers.registration._pick_active_proxy", new_callable=AsyncMock
    ) as pick_proxy:
        response = client.post(
            "/register/outlook",
            json={
                "proxy": "socks5://user:pw@9.9.9.9:1080",
                "mode": "hybrid",
                "config": {"mode": "browser"},
            },
        )

    assert response.status_code == 200
    pick_proxy.assert_not_called()
    call = runtime.submissions[0][1]
    assert call["proxy"] == "socks5://user:pw@9.9.9.9:1080"
    assert call["config"]["mode"] == "hybrid"


def test_register_google_injects_local_sms_config(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    config_entry = SimpleNamespace(value={"provider": "hero_sms", "country": "52"})
    with patch(
        "gateway.routers.registration._pick_active_proxy", new_callable=AsyncMock, return_value=""
    ), patch("config_service.service.ConfigService.get", new=AsyncMock(return_value=config_entry)):
        response = client.post("/register/google", json={})

    assert response.status_code == 200
    assert runtime.submissions[0][1]["config"]["sms"]["provider"] == "hero_sms"


def test_register_rejects_invalid_count_before_queueing(client):
    app.state.task_manager = FakeRuntime()
    response = client.post("/register/outlook", json={"count": 0})
    assert response.status_code == 422
    assert not app.state.task_manager.submissions


def test_register_rejects_unsupported_platform_before_queueing(client):
    app.state.task_manager = FakeRuntime()
    response = client.post("/register/claude", json={})
    assert response.status_code == 422
    assert not app.state.task_manager.submissions


def test_register_rejects_google_protocol_mode_before_queueing(client):
    app.state.task_manager = FakeRuntime()
    response = client.post("/register/google", json={"mode": "protocol"})
    assert response.status_code == 422
    assert not app.state.task_manager.submissions


def test_get_task_status_reads_persisted_job_only(client):
    persisted = SimpleNamespace(
        task_id="task-001",
        platform="outlook",
        status="running",
        result=None,
        error_message=None,
        created_at=None,
        updated_at=None,
        last_event_seq=0,
    )
    with patch(
        "gateway.registration_jobs.RegistrationJobService.get_by_task_id",
        new=AsyncMock(return_value=persisted),
    ):
        response = client.get("/tasks/task-001")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "task_id": "task-001",
        "platform": "outlook",
        "status": "running",
        "result": None,
        "error": None,
        "last_event_seq": 0,
        "created_at": None,
        "updated_at": None,
    }


def test_get_unknown_task_does_not_query_external_backend(client):
    response = client.get("/tasks/missing")
    assert response.status_code == 200
    assert response.json()["data"] == {"task_id": "missing", "status": "unknown"}
