from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserRead(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6)
    role: str = "readonly"


class ApiKeyRead(BaseModel):
    id: str
    key: str
    name: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None = None
    call_count: int
    model_config = {"from_attributes": True}


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1)
    scopes: list[str] = []


class AuditLogRead(BaseModel):
    operator: str
    action: str
    target: str | None = None
    before_value: Any | None = None
    after_value: Any | None = None
    ip_address: str | None = None
    created_at: datetime | None = None
    model_config = {"from_attributes": True}


class AlertRuleRead(BaseModel):
    id: str
    name: str
    rule_type: str
    threshold: str | None = None
    enabled: bool
    notify_channels: list[str]
    model_config = {"from_attributes": True}


class AlertRuleWrite(BaseModel):
    name: str
    rule_type: str
    threshold: str | None = None
    enabled: bool = True
    notify_channels: list[str] = []
