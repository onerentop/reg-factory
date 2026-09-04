from passlib.context import CryptContext

from gateway.repository import UserRepository
from gateway.schemas import LoginResponse
from shared.auth import JwtAuthStrategy

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """本机控制台登录认证。"""

    def __init__(self, user_repo: UserRepository, jwt_strategy: JwtAuthStrategy):
        self._user_repo = user_repo
        self._jwt = jwt_strategy

    async def login(self, username: str, password: str) -> LoginResponse | None:
        user = await self._user_repo.get_by_username(username)
        if user is None or not pwd_context.verify(password, user.password_hash) or not user.is_active:
            return None
        return LoginResponse(
            access_token=self._jwt.create_token(user_id=str(user.id), role=user.role),
            role=user.role,
            username=user.username,
        )

    async def create_user(self, username: str, password: str, role: str = "admin"):
        return await self._user_repo.create(
            username=username,
            password_hash=pwd_context.hash(password),
            role=role,
        )
