import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_model import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """通用仓储基类。子类设置 model_class 即可获得完整 CRUD。

    仓储模式：将数据访问逻辑从业务逻辑中分离。
    泛型：保证类型安全，IDE 可正确推导返回类型。
    """

    model_class: type[T]

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, **kwargs: Any) -> T:
        entity = self.model_class(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: uuid.UUID) -> T | None:
        stmt = select(self.model_class).where(
            self.model_class.id == entity_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_paginated(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[T], int]:
        offset = (page - 1) * page_size

        count_stmt = select(func.count()).select_from(self.model_class)
        total = (await self._session.execute(count_stmt)).scalar_one()

        items_stmt = (
            select(self.model_class)
            .offset(offset)
            .limit(page_size)
        )
        result = await self._session.execute(items_stmt)
        items = list(result.scalars().all())

        return items, total

    async def update(self, entity_id: uuid.UUID, **kwargs: Any) -> T | None:
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return None
        for key, value in kwargs.items():
            setattr(entity, key, value)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity_id: uuid.UUID) -> bool:
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False
        await self._session.delete(entity)
        await self._session.flush()
        return True
