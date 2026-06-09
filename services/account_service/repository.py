import uuid
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_repository import BaseRepository
from account_service.models import (
    Account, RegistrationStep, AccountPlatform, AccountStatus, StepStatus,
)


class AccountRepository(BaseRepository[Account]):
    model_class = Account

    async def get_with_steps(self, account_id: uuid.UUID) -> Account | None:
        stmt = (
            select(Account)
            .options(selectinload(Account.steps))
            .where(Account.id == account_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        platform: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Account], int]:
        conditions = []
        if platform:
            conditions.append(Account.platform == AccountPlatform(platform))
        if status:
            conditions.append(Account.status == AccountStatus(status))
        if keyword:
            conditions.append(Account.email.ilike(f"%{keyword}%"))

        where = and_(*conditions) if conditions else True

        count_stmt = select(func.count()).select_from(Account).where(where)
        total = (await self._session.execute(count_stmt)).scalar_one()

        items_stmt = (
            select(Account)
            .options(selectinload(Account.steps))
            .where(where)
            .order_by(Account.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(items_stmt)
        items = list(result.scalars().unique().all())

        return items, total

    async def get_by_ids(self, ids: list[uuid.UUID]) -> list[Account]:
        stmt = (
            select(Account)
            .options(selectinload(Account.steps))
            .where(Account.id.in_(ids))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def delete_batch(self, ids: list[uuid.UUID]) -> int:
        accounts = await self.get_by_ids(ids)
        for account in accounts:
            await self._session.delete(account)
        await self._session.flush()
        return len(accounts)


class StepRepository(BaseRepository[RegistrationStep]):
    model_class = RegistrationStep

    async def get_steps_for_account(self, account_id: uuid.UUID) -> list[RegistrationStep]:
        stmt = (
            select(RegistrationStep)
            .where(RegistrationStep.account_id == account_id)
            .order_by(RegistrationStep.step_number)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_steps(self, account_id: uuid.UUID, step_names: list[str]) -> list[RegistrationStep]:
        steps = []
        for i, name in enumerate(step_names, 1):
            step = RegistrationStep(
                account_id=account_id,
                step_number=i,
                name=name,
                status=StepStatus.PENDING,
            )
            self._session.add(step)
            steps.append(step)
        await self._session.flush()
        return steps
