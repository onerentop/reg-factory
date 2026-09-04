from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from tests.route_introspection import flatten_api_routes


def test_monolith_exposes_domain_routes_without_forwarding_proxy():
    routes = flatten_api_routes(app)
    paths = {path for path, _ in routes}

    # dashboard_aggregator 已随后端精简被删除，/dashboard 不再存在于路由表。
    assert {"/accounts", "/sms/providers", "/config/"} <= paths
    assert "/dashboard" not in paths
    assert not any(
        route.endpoint.__module__ == "gateway.routers.forwarding" for _, route in routes
    )


def test_monolith_has_a_single_health_endpoint():
    health_routes = [
        route for route in app.routes
        if isinstance(route, APIRoute) and route.path == "/health"
    ]

    assert len(health_routes) == 1
    assert health_routes[0].endpoint.__module__ == "app.main"



def test_monolith_serves_spa_for_non_uuid_account_platform_deep_link():
    client = TestClient(app)

    response = client.get("/accounts/outlook", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


def test_monolith_keeps_missing_static_assets_as_404():
    client = TestClient(app)

    response = client.get("/assets/missing-regfactory-asset.js")

    assert response.status_code == 404


def test_monolith_account_resource_routes_are_uuid_constrained():
    routes = flatten_api_routes(app)
    account_resource_paths = {
        path
        for path, _ in routes
        if "{account_id" in path
    }

    assert account_resource_paths == {
        "/accounts/{account_id:uuid}",
        "/accounts/{account_id:uuid}/steps",
        "/accounts/{account_id:uuid}/steps/{step_number}",
        "/api/accounts/{account_id:uuid}",
        "/api/accounts/{account_id:uuid}/steps",
        "/api/accounts/{account_id:uuid}/steps/{step_number}",
    }


def test_monolith_exposes_api_aliases_without_websocket_aliases():
    routes = flatten_api_routes(app)
    paths = {path for path, _ in routes}

    # dashboard_aggregator 已随后端精简被删除，/api/dashboard 不再存在。
    assert {"/api/accounts", "/api/sms/providers", "/api/config/"} <= paths
    assert "/api/dashboard" not in paths
    assert "/api/ws" not in paths
    assert "/api/ws/task/{task_id}/logs" not in paths


def test_monolith_keeps_account_apis_out_of_spa_fallback():
    account_id = "11111111-1111-1111-1111-111111111111"
    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/accounts/{account_id}",
        "headers": [],
    }

    matching_routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.matches(scope)[0].name == "FULL"
    ]

    assert [route.path for route in matching_routes] == ["/accounts/{account_id:uuid}"]


def test_monolith_exposes_health_aliases():
    client = TestClient(app)

    for path in ("/health", "/api/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["architecture"] == "modular-monolith"
