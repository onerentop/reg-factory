"""observability 路由行为测试。

GET /dashboard  ——  用 monkeypatch 替换 gateway.deps.dashboard.get_dashboard_data
GET /audit      ——  override get_audit_service → FakeAuditService
GET /logs       ——  override get_session + monkeypatch LogRepository.query_logs

无鉴权要求（所有三条路由均无 RoleChecker），故只测 happy path + 参数校验。
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.deps import get_audit_service, get_session
import gateway.deps as _deps
from gateway.main import app


# ──────────────────────────────────────────────
# GET /dashboard
# ──────────────────────────────────────────────

DASHBOARD_CANNED = {
    "accounts": {"total": 42},
    "sms": {"providers_count": 3},
}


def test_dashboard_happy(client):
    with patch.object(
        _deps.dashboard,
        "get_dashboard_data",
        new=AsyncMock(return_value=DASHBOARD_CANNED),
    ):
        r = client.get("/dashboard")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["accounts"]["total"] == 42
    assert data["sms"]["providers_count"] == 3


def test_dashboard_returns_200_with_error_data(client):
    """即使下游服务不可用，dashboard 本身应返回 200（aggregator 内部 catch）。"""
    error_data = {
        "accounts": {"total": 0, "error": "Account service unavailable"},
        "sms": {"providers_count": 0, "error": "SMS service unavailable"},
    }
    with patch.object(
        _deps.dashboard,
        "get_dashboard_data",
        new=AsyncMock(return_value=error_data),
    ):
        r = client.get("/dashboard")

    assert r.status_code == 200
    assert "error" in r.json()["data"]["accounts"]


# ──────────────────────────────────────────────
# Fake AuditLog 工具
# ──────────────────────────────────────────────

class FakeAuditLog:
    def __init__(self, operator="admin", action="test_action", target="t1"):
        self.operator = operator
        self.action = action
        self.target = target
        self.before_value = None
        self.after_value = None
        self.ip_address = None
        self.created_at = None

    def model_dump(self):
        return {
            "operator": self.operator,
            "action": self.action,
            "target": self.target,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "ip_address": self.ip_address,
            "created_at": None,
        }


# ──────────────────────────────────────────────
# GET /audit
# ──────────────────────────────────────────────

def test_audit_happy_empty(client):
    fake_svc = MagicMock()
    fake_svc.list_logs = AsyncMock(return_value=([], 0))
    app.dependency_overrides[get_audit_service] = lambda: fake_svc
    r = client.get("/audit")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["items"] == []
    assert body["total"] == 0


def test_audit_happy_with_items(client):
    log = FakeAuditLog(operator="admin", action="add_proxy", target="1.2.3.4")
    fake_svc = MagicMock()
    fake_svc.list_logs = AsyncMock(return_value=([log], 1))
    app.dependency_overrides[get_audit_service] = lambda: fake_svc
    r = client.get("/audit")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["operator"] == "admin"
    assert body["items"][0]["action"] == "add_proxy"


def test_audit_filter_params_forwarded(client):
    """确认 operator/action 查询参数被传给 list_logs。"""
    fake_svc = MagicMock()
    fake_svc.list_logs = AsyncMock(return_value=([], 0))
    app.dependency_overrides[get_audit_service] = lambda: fake_svc
    r = client.get("/audit?operator=admin&action=add_proxy&page=2&page_size=10")
    assert r.status_code == 200
    # 验证 list_logs 被以正确参数调用
    fake_svc.list_logs.assert_called_once_with("admin", "add_proxy", 2, 10)


def test_audit_page_size_too_large_422(client):
    """page_size > 100 → Query 校验失败 → 422。"""
    fake_svc = MagicMock()
    fake_svc.list_logs = AsyncMock(return_value=([], 0))
    app.dependency_overrides[get_audit_service] = lambda: fake_svc
    r = client.get("/audit?page_size=999")
    assert r.status_code == 422


def test_audit_page_zero_422(client):
    """page=0 → ge=1 失败 → 422。"""
    fake_svc = MagicMock()
    fake_svc.list_logs = AsyncMock(return_value=([], 0))
    app.dependency_overrides[get_audit_service] = lambda: fake_svc
    r = client.get("/audit?page=0")
    assert r.status_code == 422


# ──────────────────────────────────────────────
# Fake LogEntry 工具
# ──────────────────────────────────────────────

class FakeLogEntry:
    def __init__(self, **kw):
        self.id = uuid.uuid4()
        self.service = kw.get("service", "gateway")
        self.level = kw.get("level", "INFO")
        self.message = kw.get("message", "test msg")
        self.trace_id = kw.get("trace_id", None)
        self.account_id = kw.get("account_id", None)
        self.created_at = None


# ──────────────────────────────────────────────
# GET /logs
# ──────────────────────────────────────────────

def _override_session_with_log_results(logs, total):
    """
    将 get_session override 为 async gen，将 LogRepository.query_logs mock。
    async generator 函数（yield）是 FastAPI DI 所需形式。
    """
    class FakeSession:
        pass

    async def fake_get_session():
        yield FakeSession()

    app.dependency_overrides[get_session] = fake_get_session

    patcher = patch(
        "shared.log_repository.LogRepository.query_logs",
        new=AsyncMock(return_value=(logs, total)),
    )
    return patcher


def test_logs_happy_empty(client):
    with _override_session_with_log_results([], 0):
        r = client.get("/logs")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["items"] == []
    assert body["total"] == 0


def test_logs_happy_with_items(client):
    entry = FakeLogEntry(service="sms", level="ERROR", message="fail", trace_id="abc")
    with _override_session_with_log_results([entry], 1):
        r = client.get("/logs")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] == 1
    item = body["items"][0]
    assert item["service"] == "sms"
    assert item["level"] == "ERROR"
    assert item["message"] == "fail"
    assert item["trace_id"] == "abc"
    assert "id" in item


def test_logs_filter_params(client):
    """service/level/trace_id/keyword/page/page_size 均可传入。"""
    with _override_session_with_log_results([], 0) as mock_qlog:
        r = client.get("/logs?service=sms&level=ERROR&page=2&page_size=10")
    assert r.status_code == 200
    # 路由正常响应即可；参数传递由集成测试负责
    assert r.json()["data"]["total"] == 0


def test_logs_page_size_too_large_422(client):
    """page_size > 200 → Query le=200 失败 → 422。"""
    with _override_session_with_log_results([], 0):
        r = client.get("/logs?page_size=999")
    assert r.status_code == 422


def test_logs_page_zero_422(client):
    """page=0 → ge=1 失败 → 422。"""
    with _override_session_with_log_results([], 0):
        r = client.get("/logs?page=0")
    assert r.status_code == 422
