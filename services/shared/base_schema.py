import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class PaginationParams(BaseModel):
    """分页参数值对象。自动约束边界。"""

    page: int = Field(default=1)
    page_size: int = Field(default=20)

    @model_validator(mode="after")
    def clamp_values(self) -> "PaginationParams":
        object.__setattr__(self, "page", max(1, self.page))
        object.__setattr__(self, "page_size", max(1, min(100, self.page_size)))
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应信封。泛型支持任意 item 类型。"""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.page_size) if self.page_size > 0 else 0

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    model_config = {"from_attributes": True}


class ApiResponse(BaseModel):
    """统一 API 响应信封。"""

    success: bool = True
    data: Any = None
    message: str | None = None


class ErrorResponse(BaseModel):
    """错误响应。"""

    success: bool = False
    code: str
    message: str
    details: dict[str, Any] | None = None
