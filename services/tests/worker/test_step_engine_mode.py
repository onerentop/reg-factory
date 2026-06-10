"""测试 OutlookRegistrationFlow.execute_step 的 hybrid/browser/protocol 模式分派。

所有 mock 均通过 monkeypatch.setitem 注入**全新** ModuleType（不触碰/不变异真实模块），
teardown 时由 monkeypatch 完整还原，避免污染后续测试（如 tests/test_browser_provider.py）。
"""
import asyncio
import sys
import types
from worker.step_engine import OutlookRegistrationFlow


def _make_flow():
    # 绕过 __init__（其会调用 LegacyBridge）
    return OutlookRegistrationFlow.__new__(OutlookRegistrationFlow)


def _run(coro):
    return asyncio.run(coro)


def _fake_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def test_mode_hybrid_dispatches_to_register_outlook_hybrid(monkeypatch):
    called = {}

    async def fake_hybrid(proxy_str, idx):
        called["mode"] = "hybrid"
        return ("h@outlook.com", "Pw!", "rt")

    monkeypatch.setitem(sys.modules, "outlook_hybrid",
                        _fake_module("outlook_hybrid", register_outlook_hybrid=fake_hybrid))

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

    monkeypatch.setitem(sys.modules, "register_outlook_standalone",
                        _fake_module("register_outlook_standalone", register_outlook_protocol=fake_protocol))

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

    monkeypatch.setitem(sys.modules, "register_outlook_standalone",
                        _fake_module("register_outlook_standalone", _register_one_browser=fake_browser))

    # browser 分支会 from common.browser_provider import get_browser_provider —
    # 注入全新的 common 父包 + 子模块 stub，绝不变异真实模块。
    common_pkg = _fake_module("common")
    common_pkg.__path__ = []  # 标记为包
    monkeypatch.setitem(sys.modules, "common", common_pkg)
    monkeypatch.setitem(sys.modules, "common.browser_provider",
                        _fake_module("common.browser_provider", get_browser_provider=lambda: object()))

    flow = _make_flow()
    ctx = {"proxy": "p", "idx": 0}  # 无 mode → 默认 browser
    res = _run(flow.execute_step(2, "Browser registration with proxy", ctx))
    assert called["mode"] == "browser"
    assert res.success is True
