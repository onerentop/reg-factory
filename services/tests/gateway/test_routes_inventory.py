"""单体仅暴露 Outlook / Google 控制台所需 API 路由。"""

from app.main import app


RETAINED_PATHS = {
    "/auth/login",
    "/accounts",
    "/accounts/{account_id:uuid}",
    "/accounts/{account_id:uuid}/steps",
    "/accounts/{account_id:uuid}/steps/{step_number}",
    "/accounts/batch/delete",
    "/accounts/batch/export",
    "/proxy",
    "/proxy/{proxy_id}",
    "/proxy/{proxy_id}/status",
    "/proxy/{proxy_id}/test",
    "/register/{platform}",
    "/tasks/{task_id}",
    "/tasks/{task_id}/events",
    "/tools/extract-graph-token",
    "/ws/task/{task_id}/logs",
    "/sms/providers",
    "/sms/config",
    "/config/{key:path}",
}
REMOVED_PATHS = {
    "/alerts/rules",
    "/audit",
    "/dashboard",
    "/logs",
    "/tools/validate-keys",
    "/auth/users",
    "/auth/api-keys",
    "/accounts/import",
    "/accounts/batch/retry",
}


def _route_paths():
    return {route.path for route in app.routes if getattr(route, "path", None)}


def test_monolith_exposes_retained_routes_only():
    paths = _route_paths()
    assert RETAINED_PATHS <= paths
    assert not (REMOVED_PATHS & paths)
