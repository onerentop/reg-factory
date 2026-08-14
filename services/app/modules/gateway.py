"""Gateway 领域的单体路由适配器。"""
from app.modules.legacy_routes import select_routes
from gateway import main as legacy_gateway

# forwarding 仅服务于旧的跨服务 HTTP 拓扑，单体模式必须排除。
routes = select_routes(
    legacy_gateway.app,
    skip_paths={"/health"},
    skip_modules={"gateway.routers.forwarding"},
)
