from shared.auth.base import AuthResult, AuthStrategy


class ApiKeyAuthStrategy(AuthStrategy):
    """API Key 认证策略。从内存字典或数据库查找 Key。"""

    def __init__(self, keys: dict[str, dict]):
        self._keys = keys

    def verify(self, credential: str) -> AuthResult:
        key_info = self._keys.get(credential)
        if key_info is None:
            return AuthResult(authenticated=False, error="Invalid API key")
        return AuthResult(
            authenticated=True,
            user_id=key_info.get("user_id", ""),
            role=key_info.get("role", "service"),
            scopes=key_info.get("scopes", []),
        )
