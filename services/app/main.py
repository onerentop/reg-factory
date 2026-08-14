"""RegFactory 的统一 API 入口。

迁移期间复用现有领域服务的路由实现，但让它们共享同一个数据库、
生命周期与进程内依赖；Gateway 的 HTTP forwarding 路由不会被挂载。
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.dependencies import db, get_auth_service, jwt_strategy, settings
from shared.base_model import BaseModel
from shared.log_handler import setup_logger



@asynccontextmanager
async def lifespan(app: FastAPI):
    # 统一加载全部模型，保证开发/测试的 schema 初始化包含所有领域表。
    from account_service import models as account_models  # noqa: F401
    from config_service import models as config_models  # noqa: F401
    from gateway import models as gateway_models  # noqa: F401
    from sms_service import models as sms_models  # noqa: F401
    from worker.local_task_manager import LocalProcessTaskManager

    _ = db.engine
    if settings.should_create_schema:
        async with db.engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)

    if settings.seed_admin_user and settings.seed_admin_password:
        from gateway.repository import UserRepository

        async with db.get_session() as session:
            repo = UserRepository(session)
            if not await repo.get_by_username(settings.seed_admin_user):
                await get_auth_service(session).create_user(
                    settings.seed_admin_user,
                    settings.seed_admin_password,
                    "admin",
                )

    task_manager = LocalProcessTaskManager(settings.task_max_concurrency)
    await task_manager.mark_unfinished_interrupted()
    await task_manager.start()
    app.state.task_manager = task_manager

    logger = setup_logger("regfactory")
    logger.info("RegFactory local modular monolith starting")
    try:
        yield
    finally:
        await task_manager.stop()
        await db.close()


class SpaStaticFiles(StaticFiles):
    """已构建的 React SPA：静态资源保持 404，前端深链回退到 index.html。"""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code != 404 or Path(path).suffix:
            return response
        return await super().get_response("index.html", scope)


def _frontend_dist_dir() -> Path:
    configured = Path(settings.static_dir)
    if configured.is_absolute():
        return configured
    return (Path(__file__).resolve().parents[2] / configured).resolve()


app = FastAPI(title="RegFactory API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    """保护 REST API，并兼容 Vite 历史使用的 /api 前缀。"""
    path = request.url.path
    if (
        not settings.should_require_auth
        or request.method == "OPTIONS"
        or path in {"/health", "/auth/login", "/api/health", "/api/auth/login"}
    ):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing token"})

    principal = jwt_strategy.verify(authorization[7:])
    if not principal.authenticated:
        return JSONResponse(status_code=401, content={"detail": "Invalid token"})

    request.state.principal = principal
    return await call_next(request)


# 各领域适配器负责复用旧端点并绑定单体依赖；组合根不再了解旧服务 app 的细节。
from app.modules.accounts import routes as account_routes  # noqa: E402
from app.modules.configuration import routes as config_routes  # noqa: E402
from app.modules.gateway import routes as gateway_routes  # noqa: E402
from app.modules.sms import routes as sms_routes  # noqa: E402

# 先放领域路由，再放 Gateway 路由，避免旧 forwarding catch-all 截获请求。
domain_routes = [*account_routes, *sms_routes, *config_routes, *gateway_routes]
app.router.routes.extend(domain_routes)

# 浏览器客户端以 /api 为 base URL；保留无前缀旧路径，同时显式注册 HTTP 别名。
api_router = APIRouter()
api_router.routes.extend(route for route in domain_routes if isinstance(route, APIRoute))
app.include_router(api_router, prefix="/api")


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "regfactory", "architecture": "modular-monolith"}


@app.exception_handler(404)
async def spa_not_found_handler(request: Request, _error):
    """StaticFiles 不会把未知目录交给自身；在最后用 React 入口承接深链。"""
    if (
        request.method == "GET"
        and not request.url.path.startswith(("/api", "/ws"))
        and "text/html" in request.headers.get("accept", "")
        and frontend_dist.is_dir()
        and "." not in Path(request.url.path).name
    ):
        return FileResponse(frontend_dist / "index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


frontend_dist = _frontend_dist_dir()
if frontend_dist.is_dir():
    app.mount("/", SpaStaticFiles(directory=frontend_dist, html=True), name="frontend")
