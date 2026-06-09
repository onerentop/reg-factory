from gateway.repository import AuditLogRepository
from gateway.schemas import AuditLogRead


class AuditService:
    """操作审计业务逻辑。"""

    def __init__(self, repo: AuditLogRepository):
        self._repo = repo

    async def log_action(
        self, operator: str, action: str, target: str | None = None,
        before_value: dict | None = None, after_value: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        await self._repo.create(
            operator=operator, action=action, target=target,
            before_value=before_value, after_value=after_value,
            ip_address=ip_address,
        )

    async def list_logs(
        self, operator: str | None = None, action: str | None = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple[list[AuditLogRead], int]:
        logs, total = await self._repo.list_filtered(operator, action, page, page_size)
        return [AuditLogRead(
            operator=l.operator, action=l.action, target=l.target,
            before_value=l.before_value, after_value=l.after_value,
            ip_address=l.ip_address, created_at=l.created_at,
        ) for l in logs], total
