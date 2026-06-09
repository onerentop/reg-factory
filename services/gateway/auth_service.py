import secrets
from passlib.context import CryptContext

from shared.auth import JwtAuthStrategy, AuthResult
from gateway.repository import UserRepository, ApiKeyRepository
from gateway.schemas import LoginResponse, UserRead, ApiKeyRead


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """用户认证和 API Key 管理业务逻辑。"""

    def __init__(
        self,
        user_repo: UserRepository,
        api_key_repo: ApiKeyRepository,
        jwt_strategy: JwtAuthStrategy,
    ):
        self._user_repo = user_repo
        self._api_key_repo = api_key_repo
        self._jwt = jwt_strategy

    async def login(self, username: str, password: str) -> LoginResponse | None:
        user = await self._user_repo.get_by_username(username)
        if user is None or not pwd_context.verify(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        token = self._jwt.create_token(user_id=str(user.id), role=user.role)
        return LoginResponse(
            access_token=token, role=user.role, username=user.username,
        )

    async def create_user(self, username: str, password: str, role: str = "readonly") -> UserRead:
        hashed = pwd_context.hash(password)
        user = await self._user_repo.create(
            username=username, password_hash=hashed, role=role,
        )
        return UserRead(
            id=str(user.id), username=user.username,
            role=user.role, is_active=user.is_active,
            created_at=user.created_at,
        )

    async def list_users(self) -> list[UserRead]:
        users, _ = await self._user_repo.list_paginated(page=1, page_size=1000)
        return [UserRead(
            id=str(u.id), username=u.username, role=u.role,
            is_active=u.is_active, created_at=u.created_at,
        ) for u in users]

    async def create_api_key(self, name: str, owner_id: str, scopes: list[str]) -> ApiKeyRead:
        key_value = secrets.token_hex(32)
        key = await self._api_key_repo.create(
            key=key_value, name=name, owner_id=owner_id, scopes=scopes,
        )
        return ApiKeyRead(
            id=str(key.id), key=key.key, name=key.name,
            scopes=key.scopes, is_active=key.is_active,
            last_used_at=key.last_used_at, call_count=key.call_count,
        )

    async def revoke_api_key(self, key_id: str) -> bool:
        import uuid
        result = await self._api_key_repo.update(uuid.UUID(key_id), is_active=False)
        return result is not None

    async def list_api_keys(self, owner_id: str) -> list[ApiKeyRead]:
        keys = await self._api_key_repo.get_by_owner(owner_id)
        return [ApiKeyRead(
            id=str(k.id), key=k.key, name=k.name, scopes=k.scopes,
            is_active=k.is_active, last_used_at=k.last_used_at,
            call_count=k.call_count,
        ) for k in keys]
