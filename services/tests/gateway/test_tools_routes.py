"""tools 路由行为测试。

routes:
  POST /tools/unlock-outlook       → worker.tasks.unlock_outlook_account.delay(email, password)
  POST /tools/validate-keys        → worker.tasks.validate_session_key.delay(key)
  POST /tools/extract-graph-token  → httpx 查账户 + extract_graph_tokens.get_graph_token（executor）
  POST /tools/activate-plus        → worker.tasks.activate_plus_account.delay(access_token, email, card)

所有 Celery 任务在路由函数体内懒导入（from worker.tasks import X），
所以 patch 目标是 worker.tasks.<name>，而不是 gateway.routers.tools.<name>。
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from gateway.main import app


# ──────────────────────────────────────────────
# POST /tools/unlock-outlook
# ──────────────────────────────────────────────

def test_unlock_outlook_happy(client):
    fake_task = MagicMock()
    fake_task.id = "task-unlock-001"

    with patch("worker.tasks.unlock_outlook_account") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post("/tools/unlock-outlook", json={"email": "test@outlook.com", "password": "Pw1234"})

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["task_id"] == "task-unlock-001"
    assert data["status"] == "queued"
    mock_fn.delay.assert_called_once_with("test@outlook.com", "Pw1234")


def test_unlock_outlook_missing_fields_500(client):
    """body 缺 email/password → KeyError → 500（body: dict 无 Pydantic 校验）。"""
    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("worker.tasks.unlock_outlook_account") as mock_fn:
        mock_fn.delay.return_value = MagicMock(id="x")
        r = no_raise.post("/tools/unlock-outlook", json={})
    assert r.status_code == 500


# ──────────────────────────────────────────────
# POST /tools/validate-keys
# ──────────────────────────────────────────────

def test_validate_keys_happy(client):
    fake_task = MagicMock()
    fake_task.id = "task-validate-002"

    with patch("worker.tasks.validate_session_key") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post("/tools/validate-keys", json={"key": "sk-abc123"})

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["task_id"] == "task-validate-002"
    assert data["status"] == "queued"
    mock_fn.delay.assert_called_once_with("sk-abc123")


def test_validate_keys_missing_key_500(client):
    """缺 key → KeyError → 500。"""
    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("worker.tasks.validate_session_key") as mock_fn:
        mock_fn.delay.return_value = MagicMock(id="x")
        r = no_raise.post("/tools/validate-keys", json={})
    assert r.status_code == 500


# ──────────────────────────────────────────────
# POST /tools/activate-plus
# ──────────────────────────────────────────────

def test_activate_plus_happy(client):
    fake_task = MagicMock()
    fake_task.id = "task-plus-003"

    with patch("worker.tasks.activate_plus_account") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post(
            "/tools/activate-plus",
            json={"access_token": "tok-xyz", "email": "user@outlook.com", "card": "CARD-001"},
        )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["task_id"] == "task-plus-003"
    assert data["status"] == "queued"
    mock_fn.delay.assert_called_once_with("tok-xyz", "user@outlook.com", "CARD-001")


def test_activate_plus_no_card(client):
    """card 可选，默认空串。"""
    fake_task = MagicMock()
    fake_task.id = "task-plus-004"

    with patch("worker.tasks.activate_plus_account") as mock_fn:
        mock_fn.delay.return_value = fake_task
        r = client.post(
            "/tools/activate-plus",
            json={"access_token": "tok-xyz", "email": "user@outlook.com"},
        )

    assert r.status_code == 200
    mock_fn.delay.assert_called_once_with("tok-xyz", "user@outlook.com", "")


def test_activate_plus_missing_token_500(client):
    """缺 access_token → KeyError → 500。"""
    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("worker.tasks.activate_plus_account") as mock_fn:
        mock_fn.delay.return_value = MagicMock(id="x")
        r = no_raise.post("/tools/activate-plus", json={"email": "user@outlook.com"})
    assert r.status_code == 500


# ──────────────────────────────────────────────
# POST /tools/extract-graph-token
# ──────────────────────────────────────────────

def _make_fake_http_client(json_data: dict):
    """返回可用作 async with httpx.AsyncClient() as c: 的 mock。"""
    fake_resp = MagicMock()
    fake_resp.json.return_value = json_data

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=fake_resp)
    fake_client.put = AsyncMock(return_value=fake_resp)

    fake_ctx = AsyncMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=False)
    return fake_ctx


def _inject_extract_graph_tokens_stub(fake_result):
    """将 extract_graph_tokens 伪模块注入 sys.modules，避免 ModuleNotFoundError。
    返回 patcher，调用方负责退出。
    """
    import sys
    import types

    stub = types.ModuleType("extract_graph_tokens")
    stub.get_graph_token = MagicMock(return_value=fake_result)
    sys.modules.setdefault("extract_graph_tokens", stub)
    # 已存在时也要替换 get_graph_token，以便每次测试用新的 mock
    sys.modules["extract_graph_tokens"].get_graph_token = MagicMock(return_value=fake_result)
    return sys.modules["extract_graph_tokens"].get_graph_token


def test_extract_graph_token_happy_email_password(client):
    """直接传 email+password，不走 account_id 分支。
    extract_graph_tokens 是遗留模块，通过 sys.modules 注入 stub。
    """
    fake_token_result = {"refresh_token": "rt-abcdefghij1234567890", "client_id": "9e5f94bc-x"}
    mock_get_token = _inject_extract_graph_tokens_stub(fake_token_result)

    with patch("gateway.routers.tools._httpx.AsyncClient"), \
         patch("worker.legacy_bridge.LegacyBridge") as mock_bridge_cls, \
         patch("gateway.routers.tools.os.environ.get", return_value="http://proxy:8080"), \
         patch("asyncio.get_event_loop") as mock_loop:

        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge

        mock_executor = MagicMock()
        mock_loop.return_value = mock_executor
        mock_executor.run_in_executor = AsyncMock(return_value=fake_token_result)

        r = client.post(
            "/tools/extract-graph-token",
            json={"email": "me@outlook.com", "password": "Pass1234"},
        )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["success"] is True
    assert data["email"] == "me@outlook.com"
    assert "refresh_token" in data


def test_extract_graph_token_missing_email_password_400(client):
    """没有 email 且没有 password（也没有 account_id）→ 400。
    路由会走到 `if not email or not password: raise HTTPException(400)`，
    在那之前如果 account_id 为空则不请求上游。
    """
    with patch("worker.legacy_bridge.LegacyBridge"):
        r = client.post("/tools/extract-graph-token", json={})
    assert r.status_code == 400


def test_extract_graph_token_with_account_id_fetch(client):
    """传 account_id，路由从账户服务获取 email/password。"""
    fake_account_resp = {"data": {"email": "fetched@outlook.com", "password": "FetchedPw"}}
    fake_token_result = {"refresh_token": "rt-fetchedtoken1234567890", "client_id": "some-id"}

    _inject_extract_graph_tokens_stub(fake_token_result)
    fake_ctx = _make_fake_http_client(fake_account_resp)

    with patch("gateway.routers.tools._httpx.AsyncClient", return_value=fake_ctx), \
         patch("worker.legacy_bridge.LegacyBridge") as mock_bridge_cls, \
         patch("gateway.routers.tools.os.environ.get", return_value="http://proxy:8080"), \
         patch("asyncio.get_event_loop") as mock_loop:

        mock_bridge_cls.return_value = MagicMock()
        mock_executor = MagicMock()
        mock_loop.return_value = mock_executor
        mock_executor.run_in_executor = AsyncMock(return_value=fake_token_result)

        r = client.post(
            "/tools/extract-graph-token",
            json={"account_id": "acct-999"},
        )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["success"] is True
