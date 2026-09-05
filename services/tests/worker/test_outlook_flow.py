import asyncio
import sys
import types
from worker.flows.outlook import OutlookRegistrationFlow


def _make_flow():
    return OutlookRegistrationFlow.__new__(OutlookRegistrationFlow)  # 绕过 __init__(LegacyBridge)


def _fake_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def test_get_steps_are_legacy_kind():
    flow = _make_flow()
    steps = flow.get_steps()
    assert [s.name for s in steps] == ["Generate credentials", "Browser registration with proxy"]
    assert all(s.kind == "legacy" for s in steps)


def test_mode_protocol_dispatches(monkeypatch):
    called = {}
    def fake_protocol(proxy_str=None, idx=0):
        called["mode"] = "protocol"; return ("p@outlook.com", "Pw!")
    monkeypatch.setitem(sys.modules, "register_outlook_standalone",
                        _fake_module("register_outlook_standalone", register_outlook_protocol=fake_protocol))
    flow = _make_flow()
    ctx = {"mode": "protocol", "proxy": "p", "idx": 0}
    res = asyncio.run(flow._step_register(ctx, None))
    assert called["mode"] == "protocol" and res.success is True and ctx["email"] == "p@outlook.com"


def test_default_mode_is_browser(monkeypatch):
    called = {}
    async def fake_browser(bb, idx, proxy_str, on_window=None):
        called["mode"] = "browser"; return ("b@outlook.com", "Pw!", None)
    monkeypatch.setitem(sys.modules, "register_outlook_standalone",
                        _fake_module("register_outlook_standalone", _register_one_browser=fake_browser))
    common_pkg = _fake_module("common"); common_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "common", common_pkg)
    monkeypatch.setitem(sys.modules, "common.browser_provider",
                        _fake_module("common.browser_provider", get_browser_provider=lambda: object()))
    flow = _make_flow()
    ctx = {"proxy": "p", "idx": 0}
    res = asyncio.run(flow._step_register(ctx, None))
    assert called["mode"] == "browser" and res.success is True


async def test_outlook_flow_without_services_does_not_crash():
    """services 为 None 时（既有调用方式）流程必须照常工作。"""
    from unittest.mock import patch
    from worker.flows.outlook import OutlookRegistrationFlow

    async def _fake_register(bb, idx, proxy_str):
        return ("a@outlook.com", "pw", None)

    flow = OutlookRegistrationFlow(None)
    with patch("common.browser_provider.get_browser_provider", return_value=object()), \
         patch("register_outlook_standalone._register_one_browser", new=_fake_register):
        result = await flow._step_register(
            {"proxy": "", "idx": 0, "mode": "browser"}, flow.services)

    assert result.success
