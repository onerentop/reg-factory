"""orchestrate 路由行为测试。

routes:
  POST /orchestrate/all-platforms  → worker.tasks.register_all_platforms.delay(email, password, platforms, config)
  POST /orchestrate/full-flow      → worker.tasks.full_flow.delay(count, platforms, config)

两个任务都在函数体内懒导入（from worker.tasks import X），
所以 patch 目标是 worker.tasks.<name>。
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from gateway.main import app


# ──────────────────────────────────────────────
# POST /orchestrate/all-platforms
# ──────────────────────────────────────────────

def test_all_platforms_happy(client):
    fake_task = MagicMock()
    fake_task.id = "task-all-001"

    with patch("worker.tasks.register_all_platforms") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post(
            "/orchestrate/all-platforms",
            json={
                "email": "user@example.com",
                "password": "Pw1234",
                "platforms": ["claude", "chatgpt"],
                "config": {"headless": True},
            },
        )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["task_id"] == "task-all-001"
    assert data["status"] == "queued"
    mock_fn.delay.assert_called_once_with(
        "user@example.com",
        "Pw1234",
        ["claude", "chatgpt"],
        {"headless": True},
    )


def test_all_platforms_default_platforms(client):
    """未传 platforms → 路由默认 ['claude', 'chatgpt', 'grok']。"""
    fake_task = MagicMock()
    fake_task.id = "task-all-002"

    with patch("worker.tasks.register_all_platforms") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post(
            "/orchestrate/all-platforms",
            json={"email": "u@x.com", "password": "pw"},
        )

    assert r.status_code == 200
    call_args = mock_fn.delay.call_args[0]
    # 第三个位置参数是 platforms
    assert call_args[2] == ["claude", "chatgpt", "grok"]
    # 第四个是 config，默认为 {} (body.get("config", {}))
    assert call_args[3] == {}


def test_all_platforms_missing_email_500(client):
    """缺 email → KeyError → 500（body: dict 无 Pydantic 校验）。"""
    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("worker.tasks.register_all_platforms") as mock_fn:
        mock_fn.delay.return_value = MagicMock(id="x")
        r = no_raise.post("/orchestrate/all-platforms", json={"password": "pw"})
    assert r.status_code == 500


def test_all_platforms_missing_password_500(client):
    """缺 password → KeyError → 500。"""
    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("worker.tasks.register_all_platforms") as mock_fn:
        mock_fn.delay.return_value = MagicMock(id="x")
        r = no_raise.post("/orchestrate/all-platforms", json={"email": "u@x.com"})
    assert r.status_code == 500


# ──────────────────────────────────────────────
# POST /orchestrate/full-flow
# ──────────────────────────────────────────────

def test_full_flow_happy(client):
    fake_task = MagicMock()
    fake_task.id = "task-flow-001"

    with patch("worker.tasks.full_flow") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post(
            "/orchestrate/full-flow",
            json={
                "count": 3,
                "platforms": ["claude"],
                "config": {"mode": "browser"},
            },
        )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["task_id"] == "task-flow-001"
    assert data["status"] == "queued"
    mock_fn.delay.assert_called_once_with(3, ["claude"], {"mode": "browser"})


def test_full_flow_defaults(client):
    """未传任何字段时使用路由默认值：count=1, platforms=['claude','chatgpt','grok'], config={}。"""
    fake_task = MagicMock()
    fake_task.id = "task-flow-002"

    with patch("worker.tasks.full_flow") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post("/orchestrate/full-flow", json={})

    assert r.status_code == 200
    call_args = mock_fn.delay.call_args[0]
    assert call_args[0] == 1                                    # count
    assert call_args[1] == ["claude", "chatgpt", "grok"]       # platforms
    assert call_args[2] == {}                                   # config


def test_full_flow_task_id_in_response(client):
    """响应结构：data.task_id 和 data.status 均存在。"""
    fake_task = MagicMock()
    fake_task.id = "task-flow-003"

    with patch("worker.tasks.full_flow") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post("/orchestrate/full-flow", json={"count": 5})

    assert r.status_code == 200
    data = r.json()["data"]
    assert "task_id" in data
    assert "status" in data
    assert data["status"] == "queued"
