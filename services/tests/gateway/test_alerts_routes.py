"""alerts 路由行为测试。

GET  /alerts/rules  ——  无需鉴权，用 get_alert_engine override
POST /alerts/rules  ——  需 operator 角色；直接构造 AlertRuleRepository,
                        用 monkeypatch 覆盖其 create 方法；get_session override
                        只需返回一个空对象（repo.create 已被 mock）。
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.deps import get_alert_engine, get_session
from gateway.main import app


# ──────────────────────────────────────────────
# FakeAlertRule 工具
# ──────────────────────────────────────────────

class FakeAlertRule:
    """AlertRuleRead 期望的字段。"""
    def __init__(self, **kw):
        self.id = uuid.uuid4()
        self.name = kw.get("name", "test_rule")
        self.rule_type = kw.get("rule_type", "sms_balance")
        self.threshold = kw.get("threshold", "10.0")
        self.enabled = kw.get("enabled", True)
        self.notify_channels = kw.get("notify_channels", [])

    def model_dump(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "rule_type": self.rule_type,
            "threshold": self.threshold,
            "enabled": self.enabled,
            "notify_channels": self.notify_channels,
        }


# ──────────────────────────────────────────────
# GET /alerts/rules
# ──────────────────────────────────────────────

def test_list_alert_rules_empty(client):
    fake_engine = MagicMock()
    fake_engine.list_rules = AsyncMock(return_value=[])
    app.dependency_overrides[get_alert_engine] = lambda: fake_engine
    r = client.get("/alerts/rules")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_list_alert_rules_with_data(client):
    rule = FakeAlertRule(name="balance_low", rule_type="sms_balance", threshold="5.0")
    fake_engine = MagicMock()
    fake_engine.list_rules = AsyncMock(return_value=[rule])
    app.dependency_overrides[get_alert_engine] = lambda: fake_engine
    r = client.get("/alerts/rules")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "balance_low"
    assert data[0]["rule_type"] == "sms_balance"


# ──────────────────────────────────────────────
# POST /alerts/rules  ——  需 operator(或更高) 角色
# ──────────────────────────────────────────────

VALID_RULE_BODY = {
    "name": "low_balance",
    "rule_type": "sms_balance",
    "threshold": "5.0",
    "enabled": True,
    "notify_channels": ["email"],
}


def _override_session_for_create(rule_obj):
    """将 get_session override 为 async gen，将 AlertRuleRepository.create mock。"""
    class FakeSession:
        pass

    # 必须是 async generator 函数（yield），不能是 lambda
    async def fake_get_session():
        yield FakeSession()

    app.dependency_overrides[get_session] = fake_get_session

    patcher = patch(
        "gateway.repository.AlertRuleRepository.create",
        new=AsyncMock(return_value=rule_obj),
    )
    return patcher


def test_create_alert_rule_no_token_401(client):
    r = client.post("/alerts/rules", json=VALID_RULE_BODY)
    assert r.status_code == 401


def test_create_alert_rule_readonly_forbidden_403(client, readonly_token):
    r = client.post(
        "/alerts/rules",
        json=VALID_RULE_BODY,
        headers={"Authorization": f"Bearer {readonly_token}"},
    )
    assert r.status_code == 403


def test_create_alert_rule_operator_happy(client, admin_token):
    """admin 角色 >= operator，应可创建规则。"""
    rule_obj = FakeAlertRule(**VALID_RULE_BODY)

    with _override_session_for_create(rule_obj):
        with patch("shared.audit.AuditRecorder.record"):
            r = client.post(
                "/alerts/rules",
                json=VALID_RULE_BODY,
                headers={"Authorization": f"Bearer {admin_token}"},
            )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["name"] == "low_balance"
    assert "id" in data


def test_create_alert_rule_operator_token(client):
    """operator 角色 token 应可创建。"""
    from gateway.deps import jwt_strategy
    operator_token = jwt_strategy.create_token("op_user", "operator")
    rule_obj = FakeAlertRule(**VALID_RULE_BODY)

    with _override_session_for_create(rule_obj):
        with patch("shared.audit.AuditRecorder.record"):
            r = client.post(
                "/alerts/rules",
                json=VALID_RULE_BODY,
                headers={"Authorization": f"Bearer {operator_token}"},
            )

    assert r.status_code == 200


def test_create_alert_rule_missing_name_422(client, admin_token):
    """name 缺失 → Pydantic AlertRuleWrite 校验失败 → 422。"""
    bad_body = {"rule_type": "sms_balance"}  # 缺少必填 name
    rule_obj = FakeAlertRule(name="x", rule_type="sms_balance")

    with _override_session_for_create(rule_obj):
        r = client.post(
            "/alerts/rules",
            json=bad_body,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert r.status_code == 422


def test_create_alert_rule_missing_rule_type_422(client, admin_token):
    """rule_type 缺失 → 422。"""
    bad_body = {"name": "r1"}  # 缺少必填 rule_type
    rule_obj = FakeAlertRule(name="r1", rule_type="x")

    with _override_session_for_create(rule_obj):
        r = client.post(
            "/alerts/rules",
            json=bad_body,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert r.status_code == 422
