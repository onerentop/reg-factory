from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from shared.auth.base import AuthResult, AuthStrategy


class JwtAuthStrategy(AuthStrategy):
    """JWT 认证策略。"""

    def __init__(
        self, secret: str, algorithm: str = "HS256", expire_minutes: int = 1440
    ):
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    def create_token(self, user_id: str, role: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self._expire_minutes)
        payload = {"sub": user_id, "role": role, "exp": expire}
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify(self, credential: str) -> AuthResult:
        try:
            payload = jwt.decode(
                credential, self._secret, algorithms=[self._algorithm]
            )
            return AuthResult(
                authenticated=True,
                user_id=payload.get("sub", ""),
                role=payload.get("role", ""),
            )
        except JWTError as e:
            return AuthResult(authenticated=False, error=str(e))
