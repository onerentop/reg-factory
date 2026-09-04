from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class StepRead(BaseModel):
    step_number: int
    name: str
    status: str
    error_message: str | None = None
    duration_ms: int | None = None
    model_config = {"from_attributes": True}


class AccountRead(BaseModel):
    id: str
    email: str
    password: str | None = None
    platform: str
    status: str
    current_step: int
    total_steps: int
    error_message: str | None = None
    proxy_used: str | None = None
    tokens: dict | None = None
    created_at: datetime | None = None
    steps: list[StepRead] = []
    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    email: str = Field(min_length=1)
    password: str | None = None
    platform: Literal["outlook", "google"]
    total_steps: int = 0
    proxy_used: str | None = None
    browser_provider: str | None = None
    metadata: dict[str, Any] = {}


class AccountUpdate(BaseModel):
    password: str | None = None
    status: str | None = None
    current_step: int | None = None
    error_message: str | None = None
    cookies: dict | None = None
    tokens: dict | None = None


class StepUpdate(BaseModel):
    status: str
    error_message: str | None = None
    duration_ms: int | None = None



class BatchDeleteRequest(BaseModel):
    account_ids: list[str]


class BatchExportRequest(BaseModel):
    account_ids: list[str] = []
    format: str = "txt"
    platform: str | None = None
    status: str | None = None

