"""共享测试工具：把 FastAPI 应用/路由树摊平成真实挂载路径的 APIRoute 列表。

较新版本的 FastAPI(0.141+)在 `include_router` 时不再把子路由展开合并进
`app.routes`，而是插入一个惰性的 `_IncludedRouter` 包装节点(内部持有
`original_router` + 前缀等信息，请求匹配时才展开)。直接遍历
`app.routes` 并 `isinstance(route, APIRoute)` 过滤会漏掉所有通过
`include_router(..., prefix=...)` 挂载的路由(例如本项目 `/api/*` 别名)，
这是库行为变化，不代表这些路由被删除或失效——运行期请求仍能正确路由到它们。

这里递归展开路由树，返回 (真实完整路径, APIRoute) 列表，供测试对路由
集合做断言时使用，而不必削弱或删除对这些路由的验证。
"""
from __future__ import annotations

from fastapi.routing import APIRoute


def flatten_api_routes(app_or_router, prefix: str = "") -> list[tuple[str, APIRoute]]:
    """递归展开 `app_or_router.routes`，返回 (完整路径, APIRoute) 列表。

    非 APIRoute 的路由(如 WebSocket 路由、StaticFiles 挂载)会被跳过，
    但 `_IncludedRouter` 包装的子路由会被递归展开并带上正确前缀。
    """
    result: list[tuple[str, APIRoute]] = []
    for route in app_or_router.routes:
        if isinstance(route, APIRoute):
            result.append((prefix + route.path, route))
        elif type(route).__name__ == "_IncludedRouter":
            sub_prefix = prefix + route.include_context.prefix
            result.extend(flatten_api_routes(route.original_router, sub_prefix))
    return result
