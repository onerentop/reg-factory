"""测试注册模式解析。

只导入轻量 gateway.registration_helpers（无 FastAPI/DB 副作用），
避免导入 gateway.main 污染其它 services/tests（如 shared/test_uploaders 的事件循环）。
模式真正进入 worker config 由 gateway 路由直接调用此 helper 保证；
config→worker context→OutlookRegistrationFlow 的分派已由 test_step_engine_mode 覆盖。
"""
from gateway.registration_helpers import resolve_registration_mode


def test_toplevel_mode_takes_priority():
    assert resolve_registration_mode({"mode": "hybrid", "config": {"mode": "protocol"}}) == "hybrid"


def test_falls_back_to_config_mode():
    assert resolve_registration_mode({"config": {"mode": "protocol"}}) == "protocol"


def test_defaults_to_browser():
    assert resolve_registration_mode({"count": 1, "proxy": "p"}) == "browser"


def test_empty_body_defaults_to_browser():
    assert resolve_registration_mode({}) == "browser"


def test_none_config_is_safe():
    assert resolve_registration_mode({"config": None, "mode": "protocol"}) == "protocol"
