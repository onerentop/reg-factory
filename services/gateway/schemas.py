from typing import Any
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str




class ProxyWrite(BaseModel):
    type: str = Field(default="socks5", pattern="^(http|https|socks5)$")
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=20)
    status: str = Field(default="active", max_length=20)


class ProxyUpdate(BaseModel):
    type: str | None = Field(default=None, pattern="^(http|https|socks5)$")
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=20)


class ProxyStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=20)


class ProxyImportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    type: str = Field(default="http", pattern="^(http|https|socks5)$")
    skip_duplicates: bool = Field(default=True)


class RegistrationRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=20)
    # 兼容 API 调用方直接提供的代理；浏览器 UI 应传 proxy_id，避免暴露密码。
    proxy: str = Field(default="", max_length=1024)
    proxy_id: str | None = Field(default=None, max_length=36)
    config: dict[str, Any] = Field(default_factory=dict)
    mode: str | None = Field(default=None, max_length=32)
