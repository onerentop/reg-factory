"""auth router HTTP 行为测试：登录/用户/api-key + 鉴权(401/403)+校验(422)。"""


def test_login_happy(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    assert r.json()["data"]["access_token"] == "fake-token"


def test_login_invalid_credentials(client):
    r = client.post("/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 401


def test_login_validation_422(client):
    r = client.post("/auth/login", json={"username": ""})  # 缺 password + username 空
    assert r.status_code == 422


def test_create_user_no_token_401(client):
    r = client.post("/auth/users", json={"username": "newuser", "password": "Pw1234", "role": "readonly"})
    assert r.status_code == 401


def test_create_user_readonly_forbidden_403(client, readonly_token):
    r = client.post(
        "/auth/users",
        json={"username": "newuser", "password": "Pw1234", "role": "readonly"},
        headers={"Authorization": f"Bearer {readonly_token}"},
    )
    assert r.status_code == 403


def test_create_user_admin_happy(client, admin_token):
    r = client.post(
        "/auth/users",
        json={"username": "newuser", "password": "Pw1234", "role": "readonly"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "newuser"


def test_create_user_validation_422(client, admin_token):
    r = client.post(
        "/auth/users",
        json={"username": "ab"},  # username 过短 + 缺 password
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 422


def test_list_users_admin(client, admin_token):
    r = client.get("/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


def test_api_keys_create_list_revoke(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = client.post("/auth/api-keys", json={"name": "k", "scopes": []}, headers=h)
    assert r.status_code == 200
    r = client.get("/auth/api-keys")  # 列表无需鉴权
    assert r.status_code == 200 and isinstance(r.json()["data"], list)
    r = client.delete("/auth/api-keys/k1", headers=h)
    assert r.status_code == 200
    r = client.delete("/auth/api-keys/does-not-exist", headers=h)
    assert r.status_code == 404
