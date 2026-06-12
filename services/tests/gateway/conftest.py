"""gateway 路由行为测试的共享 fixture：TestClient + dependency_overrides + 鉴权 token。

TestClient(app) 不加 with → 不触发 lifespan(无 create_all/seed/config 网络)；
路由依赖经 app.dependency_overrides 换 fake，故不碰真 DB/服务。
"""
import pytest
from fastapi.testclient import TestClient

from gateway.main import app
from gateway.deps import get_auth_service, jwt_strategy


class _M:
    """轻量返回对象：路由对 service 返回值调 .model_dump()。"""

    def __init__(self, d):
        self._d = d

    def model_dump(self):
        return self._d


class FakeAuthService:
    async def login(self, username, password):
        if username == "admin" and password == "admin":
            return _M({"access_token": "fake-token", "role": "admin"})
        return None

    async def create_user(self, username, password, role):
        return _M({"id": "u1", "username": username, "role": role})

    async def list_users(self):
        return [_M({"id": "u1", "username": "admin", "role": "admin"})]

    async def create_api_key(self, name, owner_id, scopes):
        return _M({"id": "k1", "name": name, "key": "secret"})

    async def list_api_keys(self, owner_id):
        return [_M({"id": "k1", "name": "key", "owner_id": owner_id})]

    async def revoke_api_key(self, key_id):
        return key_id == "k1"  # k1 存在→True；其它→False(路由转 404)


@pytest.fixture
def fake_auth():
    return FakeAuthService()


@pytest.fixture
def client(fake_auth):
    app.dependency_overrides[get_auth_service] = lambda: fake_auth
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token():
    return jwt_strategy.create_token("admin", "admin")


@pytest.fixture
def readonly_token():
    return jwt_strategy.create_token("u", "readonly")
