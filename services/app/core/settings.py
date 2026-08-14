"""单体部署的集中配置。"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """只在这里读取进程配置，避免模块各自吞掉不同默认值。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///data/regfactory.db"
    jwt_secret_key: str = "dev-secret-change-me"
    seed_admin_user: str | None = None
    seed_admin_password: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    auto_create_schema: bool | None = None
    require_auth: bool | None = None
    task_max_concurrency: int = Field(default=1, ge=1, le=4)
    task_stale_after_seconds: int = Field(default=30, ge=1)
    static_dir: str = "frontend/dist"

    @model_validator(mode="after")
    def validate_local_settings(self) -> "Settings":
        if self.database_url.startswith("sqlite+"):
            prefix, separator, raw_path = self.database_url.partition("///")
            if separator and raw_path and not Path(raw_path).is_absolute():
                database_path = (Path(__file__).resolve().parents[2] / raw_path).resolve()
                database_path.parent.mkdir(parents=True, exist_ok=True)
                self.database_url = f"{prefix}///{database_path.as_posix()}"
        if self.environment.lower() == "production":
            forbidden = {"", "dev-secret-change-me", "change-me-in-production"}
            if self.jwt_secret_key in forbidden:
                raise ValueError("生产环境必须设置非默认 JWT_SECRET_KEY")
            if self.seed_admin_password in {"", "admin123"}:
                raise ValueError("生产环境必须显式设置安全的 SEED_ADMIN_PASSWORD")
        return self

    @property
    def should_create_schema(self) -> bool:
        if self.auto_create_schema is not None:
            return self.auto_create_schema
        return self.environment.lower() != "production"

    @property
    def should_require_auth(self) -> bool:
        if self.require_auth is not None:
            return self.require_auth
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
