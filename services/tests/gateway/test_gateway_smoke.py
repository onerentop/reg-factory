from gateway.main import app
from tests.route_introspection import flatten_api_routes


def test_health_ok():
    # FastAPI 0.141+ 的 include_router 会插入惰性的 _IncludedRouter 包装节点，
    # 该节点没有 `.path` 属性；直接对 app.routes 取 `.path` 会在遇到它时报
    # AttributeError。flatten_api_routes 递归展开路由树拿到真实路径集合。
    paths = {path for path, _ in flatten_api_routes(app)}
    assert "/health" in paths
