import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import DatabaseManager
from shared.log_handler import setup_logger
from shared.base_schema import ApiResponse
from shared.auth import JwtAuthStrategy
from gateway.schemas import (
    LoginRequest, UserCreate, ApiKeyCreate, AlertRuleWrite,
)
from gateway.repository import (
    UserRepository, ApiKeyRepository, AuditLogRepository,
    AlertRuleRepository, AlertHistoryRepository,
)
from gateway.auth_service import AuthService
from gateway.audit_service import AuditService
from gateway.alert_engine import AlertEngine
from gateway.dashboard_aggregator import DashboardAggregator
from gateway.websocket_hub import ws_manager

db = DatabaseManager(
    url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///regfactory_dev.db")
)

jwt_strategy = JwtAuthStrategy(
    secret=os.getenv("JWT_SECRET_KEY", "dev-secret-change-me"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = db.engine
    logger = setup_logger("gateway")
    logger.info("Gateway starting")
    yield
    await db.close()


app = FastAPI(title="RegFactory Gateway", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_session():
    async with db.get_session() as session:
        yield session


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(UserRepository(session), ApiKeyRepository(session), jwt_strategy)


def get_audit_service(session: AsyncSession = Depends(get_session)) -> AuditService:
    return AuditService(AuditLogRepository(session))


def get_alert_engine(session: AsyncSession = Depends(get_session)) -> AlertEngine:
    return AlertEngine(AlertRuleRepository(session), AlertHistoryRepository(session))


dashboard = DashboardAggregator(
    account_service_url=os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8002"),
    sms_service_url=os.getenv("SMS_SERVICE_URL", "http://localhost:8001"),
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway", "ws_connections": ws_manager.connection_count}


# --- Auth ---

@app.post("/auth/login", response_model=ApiResponse)
async def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    result = await service.login(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return ApiResponse(data=result.model_dump())


@app.post("/auth/users", response_model=ApiResponse)
async def create_user(body: UserCreate, service: AuthService = Depends(get_auth_service)):
    user = await service.create_user(body.username, body.password, body.role)
    return ApiResponse(data=user.model_dump())


@app.get("/auth/users", response_model=ApiResponse)
async def list_users(service: AuthService = Depends(get_auth_service)):
    users = await service.list_users()
    return ApiResponse(data=[u.model_dump() for u in users])


# --- API Keys ---

@app.post("/auth/api-keys", response_model=ApiResponse)
async def create_api_key(body: ApiKeyCreate, service: AuthService = Depends(get_auth_service)):
    key = await service.create_api_key(body.name, "system", body.scopes)
    return ApiResponse(data=key.model_dump())


@app.get("/auth/api-keys", response_model=ApiResponse)
async def list_api_keys(owner_id: str = "system", service: AuthService = Depends(get_auth_service)):
    keys = await service.list_api_keys(owner_id)
    return ApiResponse(data=[k.model_dump() for k in keys])


@app.delete("/auth/api-keys/{key_id}", response_model=ApiResponse)
async def revoke_api_key(key_id: str, service: AuthService = Depends(get_auth_service)):
    revoked = await service.revoke_api_key(key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return ApiResponse(message="API key revoked")


# --- Dashboard ---

@app.get("/dashboard", response_model=ApiResponse)
async def get_dashboard():
    data = await dashboard.get_dashboard_data()
    return ApiResponse(data=data)


# --- Audit ---

@app.get("/audit", response_model=ApiResponse)
async def list_audit_logs(
    operator: str | None = None, action: str | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    service: AuditService = Depends(get_audit_service),
):
    logs, total = await service.list_logs(operator, action, page, page_size)
    return ApiResponse(data={"items": [l.model_dump() for l in logs], "total": total})


# --- Alerts ---

@app.get("/alerts/rules", response_model=ApiResponse)
async def list_alert_rules(engine: AlertEngine = Depends(get_alert_engine)):
    rules = await engine.list_rules()
    return ApiResponse(data=[r.model_dump() for r in rules])


@app.post("/alerts/rules", response_model=ApiResponse)
async def create_alert_rule(
    body: AlertRuleWrite, session: AsyncSession = Depends(get_session),
):
    repo = AlertRuleRepository(session)
    rule = await repo.create(
        name=body.name, rule_type=body.rule_type, threshold=body.threshold,
        enabled=body.enabled, notify_channels=body.notify_channels,
    )
    return ApiResponse(data={"id": str(rule.id), "name": rule.name})


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


# --- Proxy Management ---
from gateway.models import ProxyEntry


@app.get("/proxy", response_model=ApiResponse)
async def list_proxies(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(select(ProxyEntry).order_by(ProxyEntry.created_at.desc()))
    proxies = result.scalars().all()
    return ApiResponse(data=[{
        "id": str(p.id), "type": p.type, "host": p.host, "port": p.port,
        "username": p.username, "status": p.status, "region": p.region,
    } for p in proxies])


@app.post("/proxy", response_model=ApiResponse)
async def add_proxy(body: dict, session: AsyncSession = Depends(get_session)):
    proxy = ProxyEntry(
        type=body.get("type", "socks5"), host=body["host"], port=int(body["port"]),
        username=body.get("username"), password=body.get("password"),
        region=body.get("region"), status="unknown",
    )
    session.add(proxy)
    await session.flush()
    await session.refresh(proxy)
    return ApiResponse(data={"id": str(proxy.id)})


@app.delete("/proxy/{proxy_id}", response_model=ApiResponse)
async def delete_proxy(proxy_id: str, session: AsyncSession = Depends(get_session)):
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    await session.delete(proxy)
    await session.flush()
    return ApiResponse(message="Deleted")
