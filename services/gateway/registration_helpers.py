"""注册路由的轻量纯逻辑助手（无 FastAPI / DB 依赖，便于隔离测试）。"""


def resolve_registration_mode(body: dict) -> str:
    """从请求体解析注册模式。

    优先级：body 顶层 mode（前端下拉）→ config.mode → 默认 "browser"。
    """
    config = body.get("config") or {}
    return body.get("mode", config.get("mode", "browser"))
