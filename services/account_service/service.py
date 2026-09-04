import uuid
from typing import Any

from account_service.models import AccountPlatform, AccountStatus, StepStatus
from account_service.repository import AccountRepository, StepRepository
from account_service.schemas import AccountRead, StepRead, AccountCreate, AccountUpdate, StepUpdate
from account_service.exporter import ExporterFactory


class AccountService:
    """账户管理业务逻辑。"""

    def __init__(self, account_repo: AccountRepository, step_repo: StepRepository):
        self._account_repo = account_repo
        self._step_repo = step_repo

    async def list_accounts(
        self, platform: str | None = None, status: str | None = None,
        keyword: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[AccountRead], int]:
        accounts, total = await self._account_repo.list_filtered(
            platform=platform, status=status, keyword=keyword,
            page=page, page_size=page_size,
        )
        return [self._to_read(a) for a in accounts], total

    async def get_account(self, account_id: str) -> AccountRead | None:
        account = await self._account_repo.get_with_steps(uuid.UUID(account_id))
        if account is None:
            return None
        return self._to_read(account)

    async def create_account(self, data: AccountCreate) -> AccountRead:
        account = await self._account_repo.create(
            email=data.email,
            password=data.password,
            platform=AccountPlatform(data.platform),
            status=AccountStatus.PENDING,
            total_steps=data.total_steps,
            proxy_used=data.proxy_used,
            browser_provider=data.browser_provider,
            metadata_=data.metadata,
        )
        return self._to_read(account)

    async def update_account(self, account_id: str, data: AccountUpdate) -> AccountRead | None:
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if "status" in updates:
            updates["status"] = AccountStatus(updates["status"])
        account = await self._account_repo.update(uuid.UUID(account_id), **updates)
        if account is None:
            return None
        return self._to_read(account)

    async def delete_account(self, account_id: str) -> bool:
        return await self._account_repo.delete(uuid.UUID(account_id))

    async def delete_batch(self, account_ids: list[str]) -> int:
        ids = [uuid.UUID(aid) for aid in account_ids]
        return await self._account_repo.delete_batch(ids)

    async def get_steps(self, account_id: str) -> list[StepRead]:
        steps = await self._step_repo.get_steps_for_account(uuid.UUID(account_id))
        return [StepRead(
            step_number=s.step_number, name=s.name, status=s.status.value,
            error_message=s.error_message, duration_ms=s.duration_ms,
        ) for s in steps]

    async def update_step(self, account_id: str, step_number: int, data: StepUpdate) -> bool:
        steps = await self._step_repo.get_steps_for_account(uuid.UUID(account_id))
        target = next((s for s in steps if s.step_number == step_number), None)
        if target is None:
            return False
        await self._step_repo.update(
            target.id,
            status=StepStatus(data.status),
            error_message=data.error_message,
            duration_ms=data.duration_ms,
        )
        return True

    async def export_accounts(
        self, format_name: str, account_ids: list[str] | None = None,
        platform: str | None = None, status: str | None = None,
    ) -> str:
        if account_ids:
            ids = [uuid.UUID(aid) for aid in account_ids]
            accounts = await self._account_repo.get_by_ids(ids)
        else:
            accounts, _ = await self._account_repo.list_filtered(
                platform=platform, status=status, page=1, page_size=10000,
            )
        data = [self._to_dict(a) for a in accounts]
        exporter = ExporterFactory.get(format_name)
        return exporter.export(data)


    def _to_read(self, account) -> AccountRead:
        steps = []
        try:
            loaded_steps = getattr(account, "steps", None)
            if loaded_steps:
                steps = [StepRead(
                    step_number=s.step_number, name=s.name, status=s.status.value,
                    error_message=s.error_message, duration_ms=s.duration_ms,
                ) for s in loaded_steps]
        except Exception:
            pass
        return AccountRead(
            id=str(account.id),
            email=account.email,
            password=account.password,
            platform=account.platform.value,
            status=account.status.value,
            current_step=account.current_step,
            total_steps=account.total_steps,
            error_message=account.error_message,
            proxy_used=account.proxy_used,
            tokens=account.tokens,
            created_at=account.created_at,
            steps=steps,
        )

    def _to_dict(self, account) -> dict:
        return {
            "email": account.email,
            "password": account.password,
            "platform": account.platform.value,
            "status": account.status.value,
            "tokens": account.tokens,
            "cookies": account.cookies,
            "created_at": account.created_at,
        }
