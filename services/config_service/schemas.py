from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConfigRead(BaseModel):
    key: str
    value: Any
    category: str
    description: str | None = None
    model_config = {"from_attributes": True}


class ConfigWrite(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    value: Any
    category: str = "general"
    description: str | None = None


class ConfigVersionRead(BaseModel):
    id: UUID
    config_key: str
    old_value: Any | None
    new_value: Any
    changed_by: str
    model_config = {"from_attributes": True}
