"""IxBrowserService：包根 _open_ixbrowser_page(async CM)，原生浏览器会话能力(Adapter)。
不改根脚本；session() 是 async CM——会话在 with 块内存活、退出自动清理。"""

from contextlib import asynccontextmanager

from worker.capabilities.interfaces import BrowserService, BrowserSession


class IxBrowserService(BrowserService):
    @asynccontextmanager
    async def session(self, *, proxy: str, idx: int = 0):
        from common.browser_provider import get_browser_provider
        from register_outlook_standalone import _open_ixbrowser_page
        bb = get_browser_provider()
        async with _open_ixbrowser_page(bb, idx, proxy) as (page, context, profile_id):
            yield BrowserSession(page=page, context=context, profile_id=profile_id, proxy=proxy)
