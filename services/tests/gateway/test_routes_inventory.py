"""路由清单不变量：把 gateway/main.py 拆成多个 router 模块前后，
全部路由 (path, methods) 必须完全不变。这是拆分重构的安全网——
现有 gateway 测试不经 HTTP 路由层，此测试确保拆分不丢/不改任何路由。
"""

from gateway.main import app

EXPECTED = {
    ("/accounts", "GET,POST"),
    ("/accounts/{path:path}", "DELETE,GET,POST,PUT"),
    ("/alerts/rules", "GET"),
    ("/alerts/rules", "POST"),
    ("/audit", "GET"),
    ("/auth/api-keys", "GET"),
    ("/auth/api-keys", "POST"),
    ("/auth/api-keys/{key_id}", "DELETE"),
    ("/auth/login", "POST"),
    ("/auth/users", "GET"),
    ("/auth/users", "POST"),
    ("/config/{path:path}", "DELETE,GET,POST,PUT"),
    ("/dashboard", "GET"),
    ("/docs", "GET,HEAD"),
    ("/docs/oauth2-redirect", "GET,HEAD"),
    ("/health", "GET"),
    ("/logs", "GET"),
    ("/openapi.json", "GET,HEAD"),
    ("/orchestrate/all-platforms", "POST"),
    ("/orchestrate/full-flow", "POST"),
    ("/proxy", "GET"),
    ("/proxy", "POST"),
    ("/proxy/{proxy_id}", "DELETE"),
    ("/proxy/{proxy_id}", "PUT"),
    ("/proxy/{proxy_id}/status", "PUT"),
    ("/proxy/{proxy_id}/test", "POST"),
    ("/redoc", "GET,HEAD"),
    ("/register/outlook", "POST"),
    ("/sms/{path:path}", "DELETE,GET,POST,PUT"),
    ("/tasks/{task_id}", "GET"),
    ("/tools/activate-plus", "POST"),
    ("/tools/extract-graph-token", "POST"),
    ("/tools/unlock-outlook", "POST"),
    ("/tools/validate-keys", "POST"),
    ("/ws", "WS"),
    ("/ws/task/{task_id}/logs", "WS"),
}


def _route_set():
    out = set()
    for r in app.routes:
        p = getattr(r, "path", None)
        if p is None:
            continue
        meth = getattr(r, "methods", None)
        out.add((p, ",".join(sorted(meth)) if meth else "WS"))
    return out


def test_all_routes_preserved():
    assert _route_set() == EXPECTED
