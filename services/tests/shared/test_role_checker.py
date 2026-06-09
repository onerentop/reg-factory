import pytest
from fastapi import HTTPException
from shared.auth import JwtAuthStrategy, RoleChecker


@pytest.fixture
def checker():
    jwt = JwtAuthStrategy(secret="test-secret")
    return RoleChecker(jwt)


def test_check_role_admin(checker):
    assert checker.check_role("admin", "admin") is True
    assert checker.check_role("admin", "operator") is True
    assert checker.check_role("admin", "readonly") is True


def test_check_role_operator(checker):
    assert checker.check_role("operator", "admin") is False
    assert checker.check_role("operator", "operator") is True
    assert checker.check_role("operator", "readonly") is True


def test_check_role_readonly(checker):
    assert checker.check_role("readonly", "admin") is False
    assert checker.check_role("readonly", "operator") is False
    assert checker.check_role("readonly", "readonly") is True
