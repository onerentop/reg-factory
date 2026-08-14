"""从过渡期服务提取可复用路由，隔离旧 FastAPI app 组合细节。"""
from collections.abc import Iterable

from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute


Route = APIRoute | APIWebSocketRoute


def iter_api_routes(source: FastAPI) -> Iterable[Route]:
    """兼容 FastAPI 既有和新版惰性 include_router 的路由容器。"""
    for route in source.router.routes:
        if isinstance(route, (APIRoute, APIWebSocketRoute)):
            yield route
            continue
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            yield from (
                nested_route
                for nested_route in included_router.routes
                if isinstance(nested_route, (APIRoute, APIWebSocketRoute))
            )


def select_routes(
    source: FastAPI,
    *,
    skip_paths: set[str] | None = None,
    skip_modules: set[str] | None = None,
) -> list[Route]:
    """按路径或端点模块筛选出应由单体注册的路由。"""
    ignored_paths = skip_paths or set()
    ignored_modules = skip_modules or set()
    return [
        route
        for route in iter_api_routes(source)
        if route.path not in ignored_paths and route.endpoint.__module__ not in ignored_modules
    ]
