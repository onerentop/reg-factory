"""account_service HTTP 路由行为测试：CRUD + batch + steps + import/export。"""

FAKE_ID = "11111111-1111-1111-1111-111111111111"
MISSING_ID = "99999999-9999-9999-9999-999999999999"


# ── /health ──────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── GET /accounts ─────────────────────────────────────────────────────────────

def test_list_accounts_happy(client):
    r = client.get("/accounts")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert isinstance(body["data"]["items"], list)
    assert body["data"]["items"][0]["email"] == "test@example.com"


def test_list_accounts_with_filters(client):
    r = client.get("/accounts?platform=outlook&status=pending&page=1&page_size=10")
    assert r.status_code == 200
    assert r.json()["data"]["page"] == 1


def test_list_accounts_bad_page_422(client):
    r = client.get("/accounts?page=0")  # ge=1 → 422
    assert r.status_code == 422


# ── GET /accounts/{id} ────────────────────────────────────────────────────────

def test_get_account_happy(client):
    r = client.get(f"/accounts/{FAKE_ID}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == FAKE_ID


def test_get_account_not_found(client):
    r = client.get(f"/accounts/{MISSING_ID}")
    assert r.status_code == 404


# ── POST /accounts ────────────────────────────────────────────────────────────

def test_create_account_happy(client):
    r = client.post("/accounts", json={"email": "new@example.com", "platform": "gmail"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["email"] == "new@example.com"
    assert body["data"]["platform"] == "gmail"


def test_create_account_missing_fields_422(client):
    r = client.post("/accounts", json={})  # email required
    assert r.status_code == 422


def test_create_account_empty_email_422(client):
    r = client.post("/accounts", json={"email": "", "platform": "gmail"})
    assert r.status_code == 422


# ── PUT /accounts/{id} ────────────────────────────────────────────────────────

def test_update_account_happy(client):
    r = client.put(f"/accounts/{FAKE_ID}", json={"status": "success"})
    assert r.status_code == 200
    assert r.json()["data"]["id"] == FAKE_ID


def test_update_account_not_found(client):
    r = client.put(f"/accounts/{MISSING_ID}", json={"status": "success"})
    assert r.status_code == 404


# ── DELETE /accounts/{id} ─────────────────────────────────────────────────────

def test_delete_account_happy(client):
    r = client.delete(f"/accounts/{FAKE_ID}")
    assert r.status_code == 200
    assert r.json()["message"] == "Deleted"


def test_delete_account_not_found(client):
    r = client.delete(f"/accounts/{MISSING_ID}")
    assert r.status_code == 404


# ── POST /accounts/batch/delete ───────────────────────────────────────────────

def test_batch_delete_happy(client):
    r = client.post("/accounts/batch/delete", json={"account_ids": [FAKE_ID]})
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] == 1


def test_batch_delete_empty(client):
    r = client.post("/accounts/batch/delete", json={"account_ids": []})
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] == 0


# ── POST /accounts/batch/export ───────────────────────────────────────────────

def test_batch_export_happy(client):
    r = client.post("/accounts/batch/export", json={"format": "txt"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert "content" in data
    assert data["format"] == "txt"


# ── POST /accounts/batch/retry ────────────────────────────────────────────────

def test_batch_retry_happy(client):
    r = client.post("/accounts/batch/retry", json={"account_ids": [FAKE_ID]})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["queued"] == 1


# ── GET /accounts/{id}/steps ──────────────────────────────────────────────────

def test_get_steps_happy(client):
    r = client.get(f"/accounts/{FAKE_ID}/steps")
    assert r.status_code == 200
    steps = r.json()["data"]
    assert isinstance(steps, list)
    assert steps[0]["step_number"] == 1


# ── PUT /accounts/{id}/steps/{n} ─────────────────────────────────────────────

def test_update_step_happy(client):
    r = client.put(
        f"/accounts/{FAKE_ID}/steps/1",
        json={"status": "success"},
    )
    assert r.status_code == 200
    assert r.json()["message"] == "Step updated"


def test_update_step_not_found(client):
    r = client.put(
        f"/accounts/{FAKE_ID}/steps/99",
        json={"status": "success"},
    )
    assert r.status_code == 404


def test_update_step_missing_status_422(client):
    r = client.put(f"/accounts/{FAKE_ID}/steps/1", json={})
    assert r.status_code == 422


# ── POST /accounts/import ─────────────────────────────────────────────────────

def test_import_accounts_happy(client):
    r = client.post(
        "/accounts/import",
        json={"platform": "gmail", "format": "txt", "content": "test@example.com:pass"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["imported"] == 1


def test_import_accounts_missing_fields_422(client):
    r = client.post("/accounts/import", json={})
    assert r.status_code == 422
