"""account_service 路由行为测试 fixture：TestClient + dependency_overrides + fake service。

TestClient(app) 不加 with → 不触发 lifespan(无 create_all/DB 网络)；
路由依赖经 app.dependency_overrides 换 fake，故不碰真 DB/服务。
"""
import pytest
from fastapi.testclient import TestClient

from account_service.main import app, get_service
from account_service.schemas import AccountRead, StepRead
from datetime import datetime

FAKE_ID = "11111111-1111-1111-1111-111111111111"


def _make_account(**kwargs) -> AccountRead:
    defaults = dict(
        id=FAKE_ID,
        email="test@example.com",
        password="secret",
        platform="outlook",
        status="pending",
        current_step=0,
        total_steps=3,
        error_message=None,
        proxy_used=None,
        tokens=None,
        created_at=datetime(2024, 1, 1),
        steps=[],
    )
    defaults.update(kwargs)
    return AccountRead(**defaults)


def _make_step(**kwargs) -> StepRead:
    defaults = dict(step_number=1, name="init", status="pending", error_message=None, duration_ms=None)
    defaults.update(kwargs)
    return StepRead(**defaults)


class FakeAccountService:
    async def list_accounts(self, platform, status, keyword, page, page_size):
        return [_make_account()], 1

    async def get_account(self, account_id):
        if account_id == FAKE_ID:
            return _make_account()
        return None

    async def create_account(self, data):
        return _make_account(email=data.email, platform=data.platform, status="pending")

    async def update_account(self, account_id, data):
        if account_id == FAKE_ID:
            return _make_account()
        return None

    async def delete_account(self, account_id):
        return account_id == FAKE_ID

    async def delete_batch(self, account_ids):
        return len(account_ids)

    async def export_accounts(self, format_name, account_ids=None, platform=None, status=None):
        return "test@example.com:secret"

    async def import_accounts(self, content, format_name, platform):
        return 1

    async def get_steps(self, account_id):
        return [_make_step()]

    async def update_step(self, account_id, step_number, data):
        return step_number == 1


@pytest.fixture
def fake_service():
    return FakeAccountService()


@pytest.fixture
def client(fake_service):
    app.dependency_overrides[get_service] = lambda: fake_service
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
