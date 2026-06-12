from fastapi import APIRouter, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession
from shared.base_schema import ApiResponse
from gateway.audit_service import AuditService
from gateway.dashboard_aggregator import DashboardAggregator
from gateway.deps import get_audit_service, get_session, dashboard

router = APIRouter()


@router.get("/dashboard", response_model=ApiResponse)
async def get_dashboard():
    data = await dashboard.get_dashboard_data()
    return ApiResponse(data=data)


@router.get("/audit", response_model=ApiResponse)
async def list_audit_logs(
    operator: str | None = None, action: str | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    service: AuditService = Depends(get_audit_service),
):
    logs, total = await service.list_logs(operator, action, page, page_size)
    return ApiResponse(data={"items": [l.model_dump() for l in logs], "total": total})


@router.get("/logs", response_model=ApiResponse)
async def query_logs(
    service: str | None = None,
    level: str | None = None,
    trace_id: str | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    from shared.log_repository import LogRepository
    repo = LogRepository(session)
    logs, total = await repo.query_logs(
        service=service, level=level, trace_id=trace_id,
        keyword=keyword, page=page, page_size=page_size,
    )
    return ApiResponse(data={
        "items": [{
            "id": str(l.id), "service": l.service, "level": l.level,
            "message": l.message, "trace_id": l.trace_id,
            "account_id": l.account_id, "created_at": str(l.created_at),
        } for l in logs],
        "total": total,
    })
