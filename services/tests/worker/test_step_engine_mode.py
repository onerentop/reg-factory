"""测试 OutlookRegistrationFlow.execute_step 的 hybrid/browser/protocol 模式分派。"""
import asyncio
import sys
import types
import pytest
from worker.step_engine import OutlookRegistrationFlow


def _make_flow():
    return OutlookRegistrationFlow.__new__(OutlookRegistrationFlow)


def _run(coro):
    return asyncio.run(coro)


def _inject_common_browser_provider(monkeypatch):
    """注入 common.browser_provider stub，避免 'No module named common' 错误。"""
    common_pkg = sys.modules.get("common") or types.ModuleType("common")
    common_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "common", common_pkg)

    bp = sys.modules.get("common.browser_provider") or types.ModuleType("common.browser_provider")
    bp.get_browser_provider = lambda: object()
    monkeypatch.setitem(sys.modules, "common.browser_provider", bp)


def test_mode_hybrid_dispatches_to_register_outlook_hybrid(monkeypatch):
    called = {}

    async def fake_hybrid(proxy_str, idx):
        called["mode"] = "hybrid"
        return ("h@outlook.com", "Pw!", "rt")

    mod = types.ModuleType("outlook_hybrid")
    mod.register_outlook_hybrid = fake_hybrid
    monkeypatch.setitem(sys.modules, "outlook_hybrid", mod)

    _inject_common_browser_provider(monkeypatch)

    flow = _make_flow()
    ctx = {"mode": "hybrid", "proxy": "p", "idx": 0}
    res = _run(flow.execute_step(2, "Browser registration with proxy", ctx))
    assert called["mode"] == "hybrid"
    assert res.success is True
    assert ctx["email"] == "h@outlook.com"
    assert ctx["refresh_token"] == "rt"


def test_mode_protocol_dispatches_to_register_outlook_protocol(monkeypatch):
    called = {}

    def fake_protocol(proxy_str=None, idx=0):
        called["mode"] = "protocol"
        return ("p@outlook.com", "Pw!")

    mod = sys.modules.get("register_outlook_standalone") or types.ModuleType("register_outlook_standalone")
    monkeypatch.setattr(mod, "register_outlook_protocol", fake_protocol, raising=False)
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", mod)

    _inject_common_browser_provider(monkeypatch)

    flow = _make_flow()
    ctx = {"mode": "protocol", "proxy": "p", "idx": 0}
    res = _run(flow.execute_step(2, "Browser registration with proxy", ctx))
    assert called["mode"] == "protocol"
    assert res.success is True
    assert ctx["email"] == "p@outlook.com"


def test_default_mode_is_browser(monkeypatch):
    called = {}

    async def fake_browser(bb, idx, proxy_str):
        called["mode"] = "browser"
        return ("b@outlook.com", "Pw!", None)

    mod = sys.modules.get("register_outlook_standalone") or types.ModuleType("register_outlook_standalone")
    monkeypatch.setattr(mod, "_register_one_browser", fake_browser, raising=False)
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", mod)

    # 确保 common 父包存在，以便 "from common.browser_provider import ..." 能被解析
    common_pkg = sys.modules.get("common") or types.ModuleType("common")
    common_pkg.__path__ = []  # 标记为包
    monkeypatch.setitem(sys.modules, "common", common_pkg)

    bp = types.ModuleType("common.browser_provider")
    bp.get_browser_provider = lambda: object()
    monkeypatch.setitem(sys.modules, "common.browser_provider", bp)

    flow = _make_flow()
    ctx = {"proxy": "p", "idx": 0}  # 无 mode → 默认 browser
    res = _run(flow.execute_step(2, "Browser registration with proxy", ctx))
    assert called["mode"] == "browser"
    assert res.success is True
