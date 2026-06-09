import pytest
from shared.database import DatabaseManager
from shared.base_model import BaseModel
from shared.auth import JwtAuthStrategy
from gateway.models import User, ApiKey
from gateway.repository import UserRepository, ApiKeyRepository
from gateway.auth_service import AuthService


@pytest.fixture
async def db():
    manager = DatabaseManager(url="sqlite+aiosqlite:///")
    async with manager.engine.begin() as conn:
        await conn.run_sync(User.__table__.create, checkfirst=True)
        await conn.run_sync(ApiKey.__table__.create, checkfirst=True)
    yield manager
    await manager.close()


@pytest.fixture
def jwt():
    return JwtAuthStrategy(secret="test-secret")


@pytest.mark.asyncio
async def test_create_user_and_login(db, jwt):
    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        user = await service.create_user("admin", "password123", "admin")
        assert user.username == "admin"
        assert user.role == "admin"

    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        result = await service.login("admin", "password123")
        assert result is not None
        assert result.role == "admin"
        assert result.access_token != ""


@pytest.mark.asyncio
async def test_login_wrong_password(db, jwt):
    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        await service.create_user("user1", "correct", "readonly")

    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        result = await service.login("user1", "wrong")
        assert result is None


@pytest.mark.asyncio
async def test_create_and_list_api_keys(db, jwt):
    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        key = await service.create_api_key("test-key", "owner-1", ["sms"])
        assert key.name == "test-key"
        assert len(key.key) == 64
        assert "sms" in key.scopes

    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        keys = await service.list_api_keys("owner-1")
        assert len(keys) == 1


@pytest.mark.asyncio
async def test_revoke_api_key(db, jwt):
    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        key = await service.create_api_key("revoke-me", "owner-2", [])
        key_id = key.id

    async with db.get_session() as session:
        service = AuthService(UserRepository(session), ApiKeyRepository(session), jwt)
        revoked = await service.revoke_api_key(key_id)
        assert revoked is True
