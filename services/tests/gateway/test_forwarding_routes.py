"""forwarding 路由行为测试。

routes（通过 _proxy_request 辅助函数转发）:
  ANY /sms/{path}            → SMS_URL/sms/{path}
  ANY /accounts              → ACCOUNT_URL/accounts
  ANY /accounts/{path}       → ACCOUNT_URL/accounts/{path}
  ANY /config/{path}         → CONFIG_URL/config/{path}

_proxy_request 使用 httpx.AsyncClient，patch 路径：
  gateway.routers.forwarding._httpx.AsyncClient

测试：happy path（200 + 响应体）、各 method、上游错误透传。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from gateway.main import app


# ──────────────────────────────────────────────
# Mock helpers
# ──────────────────────────────────────────────

def _make_httpx_mock(status_code: int = 200, json_data: dict | None = None):
    """构造 async context manager mock，模拟 httpx.AsyncClient。"""
    if json_data is None:
        json_data = {"ok": True}

    fake_resp = MagicMock()
    fake_resp.json.return_value = json_data

    fake_client = AsyncMock()
    fake_client.request = AsyncMock(return_value=fake_resp)

    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=False)

    return fake_ctx, fake_client


# ──────────────────────────────────────────────
# /sms/{path}
# ──────────────────────────────────────────────

def test_sms_get_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"items": [{"id": "s1"}]})

    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.get("/sms/providers")

    assert r.status_code == 200
    assert r.json()["items"][0]["id"] == "s1"


def test_sms_post_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"id": "sms-001", "status": "sent"})

    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.post("/sms/send", json={"phone": "+86138xxx"})

    assert r.status_code == 200
    assert r.json()["id"] == "sms-001"


def test_sms_forwarded_to_correct_url(client):
    """验证请求转发到 SMS_URL/sms/providers（不是其他服务）。"""
    from gateway.deps import _SMS_URL

    mock_ctx, mock_client = _make_httpx_mock()
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        client.get("/sms/providers")

    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["url"] == f"{_SMS_URL}/sms/providers"
    assert call_kwargs["method"] == "GET"


def test_sms_method_forwarded(client):
    """DELETE /sms/x → 请求方法为 DELETE。"""
    mock_ctx, mock_client = _make_httpx_mock(json_data={"deleted": True})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.delete("/sms/record/sms-001")

    assert r.status_code == 200
    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["method"] == "DELETE"


def test_sms_upstream_error_raises(client):
    """httpx 抛出异常 → _proxy_request 的 raise → TestClient 捕获为 500
    （使用 raise_server_exceptions=False）。"""
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    fake_ctx.__aexit__ = AsyncMock(return_value=False)

    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=fake_ctx):
        r = no_raise.get("/sms/providers")

    assert r.status_code == 500


# ──────────────────────────────────────────────
# /accounts  &  /accounts/{path}
# ──────────────────────────────────────────────

def test_accounts_get_list_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"data": [{"id": "acct-1"}]})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.get("/accounts")

    assert r.status_code == 200
    assert r.json()["data"][0]["id"] == "acct-1"


def test_accounts_post_create_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"data": {"id": "acct-new"}})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.post("/accounts", json={"email": "new@outlook.com", "password": "pw"})

    assert r.status_code == 200
    assert r.json()["data"]["id"] == "acct-new"


def test_accounts_get_single_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"data": {"id": "acct-1", "email": "x@y.com"}})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.get("/accounts/acct-1")

    assert r.status_code == 200
    assert r.json()["data"]["email"] == "x@y.com"


def test_accounts_put_update_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"data": {"id": "acct-1", "status": "success"}})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.put("/accounts/acct-1", json={"status": "success"})

    assert r.status_code == 200
    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["method"] == "PUT"


def test_accounts_forwarded_to_correct_url(client):
    """GET /accounts → ACCOUNT_URL/accounts（不带 trailing 路径）。"""
    from gateway.deps import _ACCOUNT_URL

    mock_ctx, mock_client = _make_httpx_mock()
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        client.get("/accounts")

    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["url"] == f"{_ACCOUNT_URL}/accounts"


def test_accounts_path_forwarded_to_correct_url(client):
    """GET /accounts/acct-123 → ACCOUNT_URL/accounts/acct-123。"""
    from gateway.deps import _ACCOUNT_URL

    mock_ctx, mock_client = _make_httpx_mock()
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        client.get("/accounts/acct-123")

    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["url"] == f"{_ACCOUNT_URL}/accounts/acct-123"


def test_accounts_upstream_error_raises(client):
    """账户服务不可达 → 500。"""
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
    fake_ctx.__aexit__ = AsyncMock(return_value=False)

    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=fake_ctx):
        r = no_raise.get("/accounts")

    assert r.status_code == 500


# ──────────────────────────────────────────────
# /config/{path}
# ──────────────────────────────────────────────

def test_config_get_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"key": "value"})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.get("/config/settings")

    assert r.status_code == 200
    assert r.json()["key"] == "value"


def test_config_post_happy(client):
    mock_ctx, mock_client = _make_httpx_mock(json_data={"updated": True})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.post("/config/settings", json={"timeout": 30})

    assert r.status_code == 200
    assert r.json()["updated"] is True


def test_config_forwarded_to_correct_url(client):
    """GET /config/smtp → CONFIG_URL/config/smtp。"""
    from gateway.deps import _CONFIG_URL

    mock_ctx, mock_client = _make_httpx_mock()
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        client.get("/config/smtp")

    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["url"] == f"{_CONFIG_URL}/config/smtp"


def test_config_delete_method_forwarded(client):
    """DELETE /config/key/old → method 为 DELETE。"""
    mock_ctx, mock_client = _make_httpx_mock(json_data={"deleted": True})
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        r = client.delete("/config/key/old")

    assert r.status_code == 200
    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["method"] == "DELETE"


def test_config_upstream_error_raises(client):
    """config 服务不可达 → 500。"""
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(side_effect=Exception("no route to host"))
    fake_ctx.__aexit__ = AsyncMock(return_value=False)

    no_raise = TestClient(app, raise_server_exceptions=False)
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=fake_ctx):
        r = no_raise.get("/config/any")

    assert r.status_code == 500


# ──────────────────────────────────────────────
# 通用：query params 透传
# ──────────────────────────────────────────────

def test_query_params_forwarded(client):
    """查询参数应被透传给上游（request.query_params → params=...）。"""
    mock_ctx, mock_client = _make_httpx_mock()
    with patch("gateway.routers.forwarding._httpx.AsyncClient", return_value=mock_ctx):
        client.get("/sms/list?page=2&limit=10")

    call_kwargs = mock_client.request.call_args[1]
    params = call_kwargs.get("params", {})
    assert params.get("page") == "2"
    assert params.get("limit") == "10"
