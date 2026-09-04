import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.log_handler import setup_logger
from gateway.deps import db
from gateway.routers import auth, websocket, proxy, registration, tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = db.engine
    from shared.base_model import BaseModel
    from gateway.models import User, ProxyEntry
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    # 种子 admin 用户(若不存在)，让鉴权保护端点可用
    from gateway.repository import UserRepository
    from gateway.auth_service import AuthService
    from gateway.deps import jwt_strategy
    async with db.get_session() as session:
        if not await UserRepository(session).get_by_username("admin"):
            await AuthService(UserRepository(session), jwt_strategy).create_user(
                os.getenv("SEED_ADMIN_USER", "admin"),
                os.getenv("SEED_ADMIN_PASSWORD", "admin123"), "admin")
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
    return {"status": "ok", "service": "gateway"}


app.include_router(auth.router)
app.include_router(websocket.router)
app.include_router(proxy.router)
app.include_router(registration.router)
app.include_router(tools.router)
