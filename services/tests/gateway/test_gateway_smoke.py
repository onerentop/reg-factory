from gateway.main import app


def test_health_ok():
    assert "/health" in [r.path for r in app.routes]
