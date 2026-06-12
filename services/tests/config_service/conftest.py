"""config_service 路由行为测试 fixture：TestClient + dependency_overrides + fake service。

TestClient(app) 不加 with → 不触发 lifespan(无 create_all/DB 网络)；
路由依赖经 app.dependency_overrides 换 fake，故不碰真 DB/服务。
"""
import pytest
from fastapi.testclient import TestClient

from config_service.main import app, get_service
from config_service.schemas import ConfigRead, ConfigVersionRead


def _make_config(**kwargs) -> ConfigRead:
    defaults = dict(key="app.name", value="RegFactory", category="general", description=None)
    defaults.update(kwargs)
    return ConfigRead(**defaults)


def _make_version(**kwargs) -> ConfigVersionRead:
    defaults = dict(
        config_key="app.name",
        old_value="Old",
        new_value="RegFactory",
        changed_by="system",
    )
    defaults.update(kwargs)
    return ConfigVersionRead(**defaults)


class FakeConfigService:
    async def get_all(self):
        return [_make_config()]

    async def get_by_category(self, category):
        return [_make_config(category=category)]

    async def get(self, key):
        if key == "app.name":
            return _make_config()
        return None

    async def set(self, key, value, category="general", changed_by="system"):
        return _make_config(key=key, value=value, category=category)

    async def delete(self, key):
        return key == "app.name"

    async def get_history(self, key):
        return [_make_version(config_key=key), _make_version(config_key=key, old_value="Older", new_value="Old")]


@pytest.fixture
def fake_service():
    return FakeConfigService()


@pytest.fixture
def client(fake_service):
    app.dependency_overrides[get_service] = lambda: fake_service
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
