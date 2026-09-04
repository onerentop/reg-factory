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
        "gateway.proxy_binding_service.ProxyBindingService.claim",
        new=AsyncMock(return_value=_claim("socks5://1.2.3.4:1080")),
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


def test_register_multiple_tasks_use_distinct_proxies(client):
    """一 IP 一窗口：同一批里的两个任务必须落在不同代理上。"""
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    claim_a = _claim("socks5://source-a:1080")
    claim_b = _claim("socks5://source-b:1080")
    with patch(
        "gateway.proxy_binding_service.ProxyBindingService.claim",
        new=AsyncMock(side_effect=[claim_a, claim_b]),
    ):
        response = client.post("/register/outlook", json={"count": 2})

    assert response.status_code == 200
    assert len(runtime.submissions) == 2
    used = [call[1]["proxy"] for call in runtime.submissions]
    assert used == ["socks5://source-a:1080", "socks5://source-b:1080"]
    assert len(set(used)) == 2


def test_register_uses_proxy_id_without_exposing_password(client):
    """手动指定代理时，连接串只下发给子进程，密码绝不出现在 HTTP 响应里。"""
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    proxy_id = str(uuid.uuid4())
    password = "s3cr3t-pw"
    selected = SimpleNamespace(id=uuid.uuid4(), status="active")
    claim = _claim(f"socks5://user:{password}@9.9.9.9:1080")
    with patch(
        "gateway.proxy_binding_service.ProxyBindingService.get_proxy",
        new=AsyncMock(return_value=selected),
    ) as get_proxy, patch(
        "gateway.proxy_binding_service.ProxyBindingService.claim_specific",
        new=AsyncMock(return_value=claim),
    ) as claim_specific:
        response = client.post("/register/outlook", json={"proxy_id": proxy_id})

    assert response.status_code == 200
    get_proxy.assert_awaited_once_with(proxy_id)
    assert claim_specific.await_count == 1
    assert claim_specific.await_args[0][0] == proxy_id
    assert runtime.submissions[0][1]["proxy"] == f"socks5://user:{password}@9.9.9.9:1080"
    assert password not in response.text


def test_register_uses_provided_proxy_and_mode(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    with patch(
        "gateway.proxy_binding_service.ProxyBindingService.claim", new=AsyncMock()
    ) as auto_claim:
        response = client.post(
            "/register/outlook",
            json={
                "proxy": "socks5://user:pw@9.9.9.9:1080",
                "mode": "hybrid",
                "config": {"mode": "browser"},
            },
        )

    assert response.status_code == 200
    auto_claim.assert_not_awaited()
    call = runtime.submissions[0][1]
    assert call["proxy"] == "socks5://user:pw@9.9.9.9:1080"
    assert call["config"]["mode"] == "hybrid"


def test_register_google_injects_local_sms_config(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    config_entry = SimpleNamespace(value={"provider": "hero_sms", "country": "52"})
    with patch(
        "gateway.proxy_binding_service.ProxyBindingService.claim",
        new=AsyncMock(return_value=_claim("socks5://1.2.3.4:1080")),
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


# ──────────────────────────────────────────────
# 当天一 IP 一窗口：每任务各抢一个
# ──────────────────────────────────────────────

def _claim(url):
    from gateway.proxy_binding_service import ProxyClaim
    return ProxyClaim(proxy_url=url, binding_id=uuid.uuid4(), proxy_id=uuid.uuid4())


def test_each_task_claims_a_distinct_proxy(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    claims = [_claim("http://p0:1080"), _claim("http://p1:1080"), _claim("http://p2:1080")]
    with patch("gateway.proxy_binding_service.ProxyBindingService.claim",
               new=AsyncMock(side_effect=claims)):
        response = client.post("/register/google", json={"count": 3})

    data = response.json()["data"]
    assert data["dispatched"] == 3 and data["skipped"] == 0
    used = [call[1]["proxy"] for call in runtime.submissions]
    assert len(set(used)) == 3


def test_partial_dispatch_when_pool_runs_out(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    with patch("gateway.proxy_binding_service.ProxyBindingService.claim",
               new=AsyncMock(side_effect=[_claim("http://p0:1080"), None])):
        response = client.post("/register/google", json={"count": 5})

    data = response.json()["data"]
    assert data["dispatched"] == 1 and data["skipped"] == 4
    assert "1/5" in data["message"]
    assert len(runtime.submissions) == 1


def test_no_proxy_available_dispatches_nothing(client):
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    with patch("gateway.proxy_binding_service.ProxyBindingService.claim",
               new=AsyncMock(return_value=None)):
        response = client.post("/register/google", json={"count": 2})

    data = response.json()["data"]
    assert data["dispatched"] == 0 and data["skipped"] == 2
    assert data["task_ids"] == []
    assert runtime.submissions == []


def test_manual_proxy_rejects_count_over_one(client):
    app.state.task_manager = FakeRuntime()
    response = client.post("/register/google",
                           json={"count": 2, "proxy_id": str(uuid.uuid4())})
    assert response.status_code == 422


def test_manual_proxy_unknown_id_is_404(client):
    app.state.task_manager = FakeRuntime()
    with patch("gateway.proxy_binding_service.ProxyBindingService.get_proxy",
               new=AsyncMock(return_value=None)):
        response = client.post("/register/google",
                               json={"count": 1, "proxy_id": str(uuid.uuid4())})
    assert response.status_code == 404


def test_manual_proxy_inactive_is_422(client):
    """状态不可用的代理不能被手动指定，且错误要与「今日已绑」区分开。"""
    app.state.task_manager = FakeRuntime()
    inactive = SimpleNamespace(id=uuid.uuid4(), status="unavailable")
    with patch("gateway.proxy_binding_service.ProxyBindingService.get_proxy",
               new=AsyncMock(return_value=inactive)):
        response = client.post("/register/google",
                               json={"count": 1, "proxy_id": str(uuid.uuid4())})
    assert response.status_code == 422


def test_manual_proxy_already_bound_today_is_409(client):
    app.state.task_manager = FakeRuntime()
    active = SimpleNamespace(id=uuid.uuid4(), status="active")
    with patch("gateway.proxy_binding_service.ProxyBindingService.get_proxy",
               new=AsyncMock(return_value=active)), \
         patch("gateway.proxy_binding_service.ProxyBindingService.claim_specific",
               new=AsyncMock(return_value=None)):
        response = client.post("/register/google",
                               json={"count": 1, "proxy_id": str(uuid.uuid4())})
    assert response.status_code == 409


def test_raw_proxy_string_bypasses_binding(client):
    """裸连接串路径不入池、不建绑定——它指向的代理在库里没有记录。"""
    runtime = FakeRuntime()
    app.state.task_manager = runtime
    with patch("gateway.proxy_binding_service.ProxyBindingService.claim",
               new=AsyncMock()) as auto, \
         patch("gateway.proxy_binding_service.ProxyBindingService.claim_specific",
               new=AsyncMock()) as manual:
        response = client.post("/register/outlook",
                               json={"count": 2, "proxy": "socks5://u:p@9.9.9.9:1080"})

    assert response.status_code == 200
    auto.assert_not_awaited()
    manual.assert_not_awaited()
    assert [c[1]["proxy"] for c in runtime.submissions] == [
        "socks5://u:p@9.9.9.9:1080", "socks5://u:p@9.9.9.9:1080"]
