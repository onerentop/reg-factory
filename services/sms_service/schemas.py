from typing import Any
from pydantic import BaseModel, Field


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    config_schema: dict[str, Any]
    model_config = {"from_attributes": True}


class AcquireRequest(BaseModel):
    service: str = Field(min_length=1)
    country: str = Field(min_length=1)
    provider: str | None = None
    max_price: str = "0"
    fixed_price: bool = False


class AcquireResponse(BaseModel):
    order_id: str
    phone_number: str
    provider: str


class CodeResponse(BaseModel):
    order_id: str
    code: str | None
    status: str


class BalanceResponse(BaseModel):
    provider: str
    balance: float


class PlatformConfigRead(BaseModel):
    provider_name: str
    display_name: str
    enabled: str
    priority: float
    config: dict[str, Any]
    model_config = {"from_attributes": True}


class PlatformConfigWrite(BaseModel):
    display_name: str | None = None
    enabled: str = "true"
    priority: float = 0
    config: dict[str, Any] = {}
