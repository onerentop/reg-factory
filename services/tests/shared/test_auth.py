from shared.auth.base import AuthResult
from shared.auth.jwt_strategy import JwtAuthStrategy


def test_jwt_encode_decode():
    strategy = JwtAuthStrategy(secret="test-secret", algorithm="HS256")
    token = strategy.create_token(user_id="user-1", role="admin")
    result = strategy.verify(token)
    assert result.authenticated is True
    assert result.user_id == "user-1"
    assert result.role == "admin"


def test_jwt_invalid_token():
    strategy = JwtAuthStrategy(secret="test-secret", algorithm="HS256")
    result = strategy.verify("invalid-token")
    assert result.authenticated is False


def test_auth_result_defaults():
    result = AuthResult(authenticated=False)
    assert result.user_id == ""
    assert result.role == ""
    assert result.scopes == []
