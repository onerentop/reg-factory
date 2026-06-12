import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.log_handler import setup_logger
from gateway.deps import db
from gateway.websocket_hub import ws_manager

from gateway.routers import auth, observability, alerts, websocket, proxy, forwarding, registration, tools, orchestrate


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = db.engine
    from shared.base_model import BaseModel
    from gateway.models import User, ApiKey, AuditLog, AlertRule, AlertHistory, ProxyEntry
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway", "ws_connections": ws_manager.connection_count}


app.include_router(auth.router)
app.include_router(observability.router)
app.include_router(alerts.router)
app.include_router(websocket.router)
app.include_router(proxy.router)
app.include_router(forwarding.router)
app.include_router(registration.router)
app.include_router(tools.router)
app.include_router(orchestrate.router)
