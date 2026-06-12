import asyncio
import sys
import types
from contextlib import asynccontextmanager
from worker.capabilities.browser import IxBrowserService
from worker.capabilities.interfaces import BrowserService, BrowserSession


def _install_fakes(monkeypatch, fake_open, provider="BB"):
    root = types.ModuleType("register_outlook_standalone")
    root._open_ixbrowser_page = fake_open
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", root)
    common = types.ModuleType("common"); common.__path__ = []
    monkeypatch.setitem(sys.modules, "common", common)
    bp = types.ModuleType("common.browser_provider")
    bp.get_browser_provider = lambda: provider
    monkeypatch.setitem(sys.modules, "common.browser_provider", bp)


def test_is_browser_service():
    assert isinstance(IxBrowserService(), BrowserService)


def test_session_wraps_open_ixbrowser_page(monkeypatch):
    events = []

    @asynccontextmanager
    async def fake_open(bb, idx, proxy):
        events.append(("open", bb, idx, proxy))
        yield ("PAGE", "CTX", "PID-123")
        events.append(("closed",))

    _install_fakes(monkeypatch, fake_open, provider="BB")

    async def run():
        svc = IxBrowserService()
        async with svc.session(proxy="px", idx=7) as sess:
            assert isinstance(sess, BrowserSession)
            assert sess.page == "PAGE" and sess.context == "CTX"
            assert sess.profile_id == "PID-123" and sess.proxy == "px"
            events.append(("inside",))

    asyncio.run(run())
    assert events[0] == ("open", "BB", 7, "px")
    assert ("inside",) in events
    assert events[-1] == ("closed",)   # 退出 with 触发底层清理
