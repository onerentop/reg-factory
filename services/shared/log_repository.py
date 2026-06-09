from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_repository import BaseRepository
from shared.log_models import LogEntry


class LogRepository(BaseRepository[LogEntry]):
    model_class = LogEntry

    async def query_logs(
        self,
        service: str | None = None,
        level: str | None = None,
        trace_id: str | None = None,
        account_id: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[LogEntry], int]:
        conditions = []
        if service:
            conditions.append(LogEntry.service == service)
        if level:
            conditions.append(LogEntry.level == level)
        if trace_id:
            conditions.append(LogEntry.trace_id == trace_id)
        if account_id:
            conditions.append(LogEntry.account_id == account_id)
        if keyword:
            conditions.append(LogEntry.message.ilike(f"%{keyword}%"))

        where = and_(*conditions) if conditions else True

        count_stmt = select(func.count()).select_from(LogEntry).where(where)
        total = (await self._session.execute(count_stmt)).scalar_one()

        items_stmt = (
            select(LogEntry)
            .where(where)
            .order_by(desc(LogEntry.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(items_stmt)
        return list(result.scalars().all()), total
