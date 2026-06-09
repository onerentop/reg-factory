from shared.auth.base import AuthResult
from shared.auth.jwt_strategy import JwtAuthStrategy
from shared.auth.api_key_strategy import ApiKeyAuthStrategy


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


def test_api_key_valid():
    keys = {"key-123": {"user_id": "svc-1", "role": "service", "scopes": ["sms"]}}
    strategy = ApiKeyAuthStrategy(keys=keys)
    result = strategy.verify("key-123")
    assert result.authenticated is True
    assert result.user_id == "svc-1"
    assert "sms" in result.scopes


def test_api_key_invalid():
    strategy = ApiKeyAuthStrategy(keys={})
    result = strategy.verify("nonexistent")
    assert result.authenticated is False


def test_auth_result_defaults():
    result = AuthResult(authenticated=False)
    assert result.user_id == ""
    assert result.role == ""
    assert result.scopes == []
