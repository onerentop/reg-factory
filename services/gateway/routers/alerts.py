from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession
from shared.base_schema import ApiResponse
from shared.auth import RoleChecker, AuthResult
from gateway.schemas import AlertRuleWrite
from gateway.alert_engine import AlertEngine
from gateway.repository import AlertRuleRepository
from gateway.deps import get_alert_engine, get_session, jwt_strategy

router = APIRouter()
role_checker = RoleChecker(jwt_strategy)


@router.get("/alerts/rules", response_model=ApiResponse)
async def list_alert_rules(engine: AlertEngine = Depends(get_alert_engine)):
    rules = await engine.list_rules()
    return ApiResponse(data=[r.model_dump() for r in rules])


@router.post("/alerts/rules", response_model=ApiResponse)
async def create_alert_rule(
    body: AlertRuleWrite, session: AsyncSession = Depends(get_session),
    _auth: AuthResult = Depends(role_checker.require_role("operator")),
):
    repo = AlertRuleRepository(session)
    rule = await repo.create(
        name=body.name, rule_type=body.rule_type, threshold=body.threshold,
        enabled=body.enabled, notify_channels=body.notify_channels,
    )
    from shared.audit import AuditRecorder
    AuditRecorder().record(operator="system", action="create_alert_rule", target=body.name)
    return ApiResponse(data={"id": str(rule.id), "name": rule.name})
