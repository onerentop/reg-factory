import pytest
from pydantic import ValidationError

from app.core.settings import Settings


def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@db/regfactory",
            jwt_secret_key="dev-secret-change-me",
        )


def test_production_allows_local_sqlite_database():
    settings = Settings(
        environment="production",
        database_url="sqlite+aiosqlite:///regfactory.db",
        jwt_secret_key="a-real-secret",
    )
    assert settings.database_url.startswith("sqlite+")


def test_production_defaults_to_auth_and_migration_managed_schema():
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://user:pass@db/regfactory",
        jwt_secret_key="a-real-secret",
    )

    assert settings.should_require_auth is True
    assert settings.should_create_schema is False
