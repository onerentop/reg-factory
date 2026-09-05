"""单体注册 API：只验证本机任务投递与 SQLite 状态查询，不执行浏览器流程。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
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
    response = client.post(
        "/register/outlook",
        json={"config": {"headless": True}, "proxy": "socks5://1.2.3.4:1080"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert data["count"] == 1
    assert len(data["task_ids"]) == 1
    task_id, call = runtime.submissions[0]
    assert task_id == data["task_ids"][0]
    assert call["platform"] == "outlook"
    assert call["config"]["mode"] == "browser"
    assert "1.2.3.4:1080" in call["proxy"]


def test_register_outlook_rotates_sid_per_window(client):
    """改回 1024proxy：count=2 每窗轮换 sid → 不同出口 IP，上游 host 不变。"""
    import re
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    base = "socks5://sb7f3017-region-Rand-sid-ORIG1234-t-5:pw@us.1024proxy.io:3000"
    response = client.post("/register/outlook", json={"count": 2, "proxy": base})
    assert response.status_code == 200
    used = [call[1]["proxy"] for call in runtime.submissions]
    assert len(used) == 2
    sids = [re.search(r"-sid-([A-Za-z0-9]+)-t-", p).group(1) for p in used]
    assert sids[0] != sids[1]
    assert all("us.1024proxy.io:3000" in p for p in used)
    assert all(p.startswith("socks5://sb7f3017-region-Rand-sid-") for p in used)
    assert base not in used


def test_register_uses_proxy_id_without_exposing_password(client):
    """手动指定代理时，连接串只下发给子进程，密码绝不出现在 HTTP 响应里。"""
    from gateway.models import ProxyEntry

    runtime = FakeRuntime()
    app.state.task_manager = runtime
    proxy_id = str(uuid.uuid4())
    password = "s3cr3t-pw"
    entry = ProxyEntry(
        type="socks5", host="9.9.9.9", port=1080,
        username="u", password=password, status="active",
    )

    class _FakeResult:
        def scalar_one_or_none(self):
            return entry

    class _FakeSession:
        async def execute(self, *_args, **_kwargs):
            return _FakeResult()

        async def commit(self):
            return None

    app.dependency_overrides[get_session] = lambda: _FakeSession()
    try:
        response = client.post("/register/outlook", json={"count": 1, "proxy_id": proxy_id})
    finally:
        app.dependency_overrides[get_session] = lambda: None

    assert response.status_code == 200
    assert password not in response.text
    call = runtime.submissions[0][1]
    assert password in call["proxy"]
    assert "9.9.9.9:1080" in call["proxy"]


def test_register_unknown_proxy_id_is_404(client):
    """proxy_id 是合法 UUID 但代理池里查不到对应记录 → 404。"""
    runtime = FakeRuntime()
    app.state.task_manager = runtime

    class _FakeResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        async def execute(self, *_args, **_kwargs):
            return _FakeResult()

        async def commit(self):
            return None

    app.dependency_overrides[get_session] = lambda: _FakeSession()
    try:
        response = client.post(
            "/register/outlook", json={"count": 1, "proxy_id": str(uuid.uuid4())}
        )
    finally:
        app.dependency_overrides[get_session] = lambda: None

    assert response.status_code == 404


def test_register_invalid_proxy_id_is_422(client):
    """proxy_id 不是合法 UUID → 422，且不查库直接拒绝。"""
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    response = client.post(
        "/register/outlook", json={"count": 1, "proxy_id": "not-a-uuid"}
    )
    assert response.status_code == 422


def test_register_top_level_mode_overrides_config_mode(client):
    """顶层 mode 覆盖 config.mode 的解析逻辑与代理无关，直接传显式代理串单独守住。"""
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    response = client.post(
        "/register/outlook",
        json={"mode": "hybrid", "config": {"mode": "browser"}, "proxy": "socks5://1.2.3.4:1080"},
    )

    assert response.status_code == 200
    call = runtime.submissions[0][1]
    assert call["proxy"] == "socks5://1.2.3.4:1080"
    assert call["config"]["mode"] == "hybrid"


def test_register_google_injects_local_sms_config(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    config_entry = SimpleNamespace(value={"provider": "hero_sms", "country": "52"})
    with patch("config_service.service.ConfigService.get", new=AsyncMock(return_value=config_entry)):
        response = client.post("/register/google", json={"proxy": "socks5://1.2.3.4:1080"})

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
