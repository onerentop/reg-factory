"""sms_service HTTP 路由行为测试：providers/balance/acquire/code/complete/cancel/config。"""


# ── /health ──────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── GET /sms/providers ────────────────────────────────────────────────────────

def test_list_providers_happy(client):
    r = client.get("/sms/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


# ── GET /sms/providers/{name}/balance ────────────────────────────────────────

def test_get_balance_happy(client):
    r = client.get("/sms/providers/smsactivate/balance")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["provider"] == "smsactivate"
    assert data["balance"] == 99.5


def test_get_balance_not_found(client):
    r = client.get("/sms/providers/unknownprovider/balance")
    assert r.status_code == 404


# ── POST /sms/number/acquire ─────────────────────────────────────────────────

def test_acquire_number_happy(client):
    r = client.post(
        "/sms/number/acquire",
        json={"service": "gmail", "country": "ru"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["order_id"] == "order-001"
    assert data["phone_number"] == "+79001234567"
    assert data["provider"] == "smsactivate"


def test_acquire_number_bad_provider_400(client):
    r = client.post(
        "/sms/number/acquire",
        json={"service": "gmail", "country": "ru", "provider": "badprovider"},
    )
    assert r.status_code == 400


def test_acquire_number_missing_fields_422(client):
    r = client.post("/sms/number/acquire", json={})
    assert r.status_code == 422


def test_acquire_number_empty_service_422(client):
    r = client.post("/sms/number/acquire", json={"service": "", "country": "ru"})
    assert r.status_code == 422


# ── GET /sms/number/{order_id}/code ──────────────────────────────────────────

def test_get_code_happy(client):
    r = client.get("/sms/number/order-001/code")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["order_id"] == "order-001"
    assert data["code"] == "123456"
    assert data["status"] == "received"


def test_get_code_not_found(client):
    r = client.get("/sms/number/missing-order/code")
    assert r.status_code == 404


# ── POST /sms/number/{order_id}/complete ─────────────────────────────────────

def test_complete_order_happy(client):
    r = client.post("/sms/number/order-001/complete")
    assert r.status_code == 200
    assert r.json()["message"] == "Completed"


def test_complete_order_not_found(client):
    r = client.post("/sms/number/missing-order/complete")
    assert r.status_code == 404


# ── POST /sms/number/{order_id}/cancel ───────────────────────────────────────

def test_cancel_order_happy(client):
    r = client.post("/sms/number/order-001/cancel")
    assert r.status_code == 200
    assert r.json()["message"] == "Cancelled"


def test_cancel_order_not_found(client):
    r = client.post("/sms/number/missing-order/cancel")
    assert r.status_code == 404


# ── GET /sms/config ───────────────────────────────────────────────────────────

def test_get_configs_happy(client):
    r = client.get("/sms/config")
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)
    assert data[0]["provider_name"] == "smsactivate"
    assert data[0]["enabled"] == "true"


# ── PUT /sms/config/{provider_name} ──────────────────────────────────────────

def test_save_config_happy(client):
    r = client.put(
        "/sms/config/smsactivate",
        json={"display_name": "SMS Activate", "enabled": "true", "priority": 1.0, "config": {"api_key": "abc"}},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["provider_name"] == "smsactivate"
    assert data["config"]["api_key"] == "abc"


def test_save_config_minimal_happy(client):
    # PlatformConfigWrite has all optional fields with defaults
    r = client.put("/sms/config/smsactivate", json={})
    assert r.status_code == 200


# ── GET /sms/providers/{name}/prices ─────────────────────────────────────────

def test_get_prices_route(client):
    from sms_service.main import app, get_service
    class _Svc:
        async def get_prices(self, name, service):
            return [{"country": "52", "cost": 0.1, "count": 100}]
    app.dependency_overrides[get_service] = lambda: _Svc()
    r = client.get("/sms/providers/hero_sms/prices?service=go")
    app.dependency_overrides.pop(get_service, None)
    assert r.status_code == 200
    assert r.json()["data"][0]["country"] == "52"


def test_get_prices_bad_provider_400(client):
    from sms_service.main import app, get_service
    class _Svc:
        async def get_prices(self, name, service):
            raise ValueError("Platform 'x' not configured")
    app.dependency_overrides[get_service] = lambda: _Svc()
    r = client.get("/sms/providers/x/prices?service=go")
    app.dependency_overrides.pop(get_service, None)
    assert r.status_code == 400
