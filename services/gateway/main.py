import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import DatabaseManager
from shared.log_handler import setup_logger
from shared.base_schema import ApiResponse
from shared.auth import JwtAuthStrategy, RoleChecker, AuthResult
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
role_checker = RoleChecker(jwt_strategy)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = db.engine
    from shared.config_client import ConfigClient
    config_client = ConfigClient(config_service_url=os.getenv("CONFIG_SERVICE_URL", "http://localhost:8003"))
    await config_client.load_from_service()
    app.state.config_client = config_client
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
async def create_user(body: UserCreate, service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    user = await service.create_user(body.username, body.password, body.role)
    from shared.audit import AuditRecorder
    recorder = AuditRecorder()
    recorder.record(operator="system", action="create_user", target=body.username)
    return ApiResponse(data=user.model_dump())


@app.get("/auth/users", response_model=ApiResponse)
async def list_users(service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    users = await service.list_users()
    return ApiResponse(data=[u.model_dump() for u in users])


# --- API Keys ---

@app.post("/auth/api-keys", response_model=ApiResponse)
async def create_api_key(body: ApiKeyCreate, service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    key = await service.create_api_key(body.name, "system", body.scopes)
    return ApiResponse(data=key.model_dump())


@app.get("/auth/api-keys", response_model=ApiResponse)
async def list_api_keys(owner_id: str = "system", service: AuthService = Depends(get_auth_service)):
    keys = await service.list_api_keys(owner_id)
    return ApiResponse(data=[k.model_dump() for k in keys])


@app.delete("/auth/api-keys/{key_id}", response_model=ApiResponse)
async def revoke_api_key(key_id: str, service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    revoked = await service.revoke_api_key(key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    from shared.audit import AuditRecorder
    recorder = AuditRecorder()
    recorder.record(operator="system", action="revoke_api_key", target=key_id)
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


# --- Logs ---

@app.get("/logs", response_model=ApiResponse)
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


# --- Alerts ---

@app.get("/alerts/rules", response_model=ApiResponse)
async def list_alert_rules(engine: AlertEngine = Depends(get_alert_engine)):
    rules = await engine.list_rules()
    return ApiResponse(data=[r.model_dump() for r in rules])


@app.post("/alerts/rules", response_model=ApiResponse)
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


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


@app.websocket("/ws/task/{task_id}/logs")
async def task_logs_websocket(websocket: WebSocket, task_id: str):
    """实时推送任务日志到前端。订阅 Redis Pub/Sub 频道 task:{task_id}:logs。"""
    await websocket.accept()
    import redis.asyncio as aioredis
    import json as _json
    try:
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        pubsub = r.pubsub()
        channel = f"task:{task_id}:logs"
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                await websocket.send_text(data)
                parsed = _json.loads(data)
                if parsed.get("type") == "done":
                    break
        await pubsub.unsubscribe(channel)
        await r.aclose()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(_json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


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
async def add_proxy(body: dict, session: AsyncSession = Depends(get_session), _auth: AuthResult = Depends(role_checker.require_role("operator"))):
    proxy = ProxyEntry(
        type=body.get("type", "socks5"), host=body["host"], port=int(body["port"]),
        username=body.get("username"), password=body.get("password"),
        region=body.get("region"), status="unknown",
    )
    session.add(proxy)
    await session.flush()
    await session.refresh(proxy)
    from shared.audit import AuditRecorder
    AuditRecorder().record(operator="system", action="add_proxy", target=body.get("host", ""))
    return ApiResponse(data={"id": str(proxy.id)})


@app.delete("/proxy/{proxy_id}", response_model=ApiResponse)
async def delete_proxy(proxy_id: str, session: AsyncSession = Depends(get_session), _auth: AuthResult = Depends(role_checker.require_role("operator"))):
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    await session.delete(proxy)
    await session.flush()
    from shared.audit import AuditRecorder
    recorder = AuditRecorder()
    recorder.record(operator="system", action="delete_proxy", target=proxy_id)
    return ApiResponse(message="Deleted")


# --- Service Proxy Routes ---
import httpx as _httpx

_SMS_URL = os.getenv("SMS_SERVICE_URL", "http://localhost:8001")
_ACCOUNT_URL = os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8002")
_CONFIG_URL = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8003")


async def _proxy_request(request: Request, target_base: str, path: str) -> dict:
    """通用代理转发。"""
    async with _httpx.AsyncClient(timeout=30) as client:
        url = f"{target_base}{path}"
        body = await request.body()
        resp = await client.request(
            method=request.method,
            url=url,
            content=body if body else None,
            headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
            params=dict(request.query_params),
        )
        return resp.json()


@app.api_route("/sms/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_sms(request: Request, path: str):
    return await _proxy_request(request, _SMS_URL, f"/sms/{path}")


@app.api_route("/accounts", methods=["GET", "POST"])
@app.api_route("/accounts/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_accounts(request: Request, path: str = ""):
    target = f"/accounts/{path}" if path else "/accounts"
    return await _proxy_request(request, _ACCOUNT_URL, target)


@app.api_route("/config/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_config(request: Request, path: str):
    return await _proxy_request(request, _CONFIG_URL, f"/config/{path}")


# --- Registration Trigger ---

@app.post("/register/outlook", response_model=ApiResponse)
async def trigger_outlook_registration(body: dict = {}):
    """从前端触发 Outlook 注册。"""
    from worker.tasks import register_outlook_new
    count = body.get("count", 1)
    proxy = body.get("proxy", "")
    config = body.get("config", {})
    task = register_outlook_new.delay(count, proxy, config)
    return ApiResponse(data={"task_id": task.id, "status": "queued", "count": count})


@app.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task_status(task_id: str):
    """查询 Celery 任务状态和结果。"""
    from worker.tasks import celery_app as _celery
    result = _celery.AsyncResult(task_id)
    data = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
    }
    if result.ready():
        if result.successful():
            data["result"] = result.result
        else:
            data["error"] = str(result.result)
    return ApiResponse(data=data)


# --- Operations Tools ---

@app.post("/tools/unlock-outlook", response_model=ApiResponse)
async def unlock_outlook(body: dict):
    from worker.tasks import unlock_outlook_account
    task = unlock_outlook_account.delay(body["email"], body["password"])
    return ApiResponse(data={"task_id": task.id, "status": "queued"})


@app.post("/tools/validate-keys", response_model=ApiResponse)
async def validate_keys(body: dict):
    from worker.tasks import validate_session_key
    task = validate_session_key.delay(body["key"])
    return ApiResponse(data={"task_id": task.id, "status": "queued"})


@app.post("/tools/extract-graph-token", response_model=ApiResponse)
async def extract_graph_token_api(body: dict):
    """提取 Outlook Graph API refresh_token（纯 HTTP，无需浏览器）。
    传 account_id 自动从 Account Service 查密码；或直接传 email+password。"""
    email = body.get("email", "")
    password = body.get("password", "")
    account_id = body.get("account_id", "")

    if account_id and not password:
        try:
            async with _httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{_ACCOUNT_URL}/accounts/{account_id}")
                acct = resp.json().get("data", {})
                email = email or acct.get("email", "")
                password = acct.get("password", "")
        except Exception:
            pass

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")

    import asyncio
    from worker.legacy_bridge import LegacyBridge
    bridge = LegacyBridge()
    bridge.ensure_importable()
    try:
        import config as _lc  # noqa
    except Exception:
        pass

    import os
    if not os.environ.get("HTTPS_PROXY"):
        os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:7897")
        os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:7897")

    from extract_graph_tokens import get_graph_token
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, get_graph_token, email, password, 0)

    if result and result.get("refresh_token"):
        client_id = result.get("client_id", "9e5f94bc-e8a4-4e73-b8be-63364c29d753")
        if account_id:
            try:
                async with _httpx.AsyncClient(timeout=10) as client:
                    await client.put(f"{_ACCOUNT_URL}/accounts/{account_id}", json={
                        "tokens": {
                            "refresh_token": result["refresh_token"],
                            "client_id": client_id,
                        },
                    })
            except Exception:
                pass
        return ApiResponse(data={
            "success": True, "email": email,
            "client_id": client_id,
            "refresh_token": result["refresh_token"][:20] + "...",
        })

    return ApiResponse(data={"success": False, "email": email, "error": str(result) if result else "Failed to get token"})


@app.post("/tools/activate-plus", response_model=ApiResponse)
async def activate_plus(body: dict):
    from worker.tasks import activate_plus_account
    task = activate_plus_account.delay(body["access_token"], body["email"], body.get("card", ""))
    return ApiResponse(data={"task_id": task.id, "status": "queued"})


# --- Orchestration ---

@app.post("/orchestrate/all-platforms", response_model=ApiResponse)
async def orchestrate_all_platforms(body: dict):
    from worker.tasks import register_all_platforms
    task = register_all_platforms.delay(
        body["email"], body["password"],
        body.get("platforms", ["claude", "chatgpt", "grok"]),
        body.get("config", {}),
    )
    return ApiResponse(data={"task_id": task.id, "status": "queued"})


@app.post("/orchestrate/full-flow", response_model=ApiResponse)
async def orchestrate_full_flow(body: dict):
    from worker.tasks import full_flow
    task = full_flow.delay(
        body.get("count", 1),
        body.get("platforms", ["claude", "chatgpt", "grok"]),
        body.get("config", {}),
    )
    return ApiResponse(data={"task_id": task.id, "status": "queued"})
