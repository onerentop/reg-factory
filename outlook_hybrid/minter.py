"""浏览器侧：过 PerimeterX → 让 Arkose JS 铸 HSol → 路由拦截截获 CreateAccount → abort（不建号）。"""

import asyncio
import json

from .credential import MintedCredential
from .errors import MintFailed


async def install_create_account_interceptor(page):
    """在 page 上挂 CreateAccount 路由拦截器（await 确保注册完成，避免与导航竞态）。

    返回一个 asyncio.Future，截获到第一个 CreateAccount 请求时 set_result
    {"payload": dict, "headers": dict}，并对所有 CreateAccount 请求 abort。
    """
    fut: asyncio.Future = asyncio.get_event_loop().create_future()

    async def _intercept(route):
        req = route.request
        if not fut.done():
            try:
                payload = json.loads(req.post_data or "{}")
            except Exception:
                payload = {}
            fut.set_result({"payload": payload, "headers": dict(req.headers)})
        try:
            await route.abort()
        except Exception:
            pass

    await page.route("**/API/CreateAccount*", _intercept)
    return fut


class SessionMinter:
    """复用 register_outlook 跑表单+过 PerimeterX，仅加拦截器截获凭证。"""

    def __init__(self, browser_provider, capture_timeout=420):
        self._bb = browser_provider
        self._timeout = capture_timeout

    async def mint(self, proxy: str, idx: int = 0) -> MintedCredential:
        from register_outlook_standalone import _open_ixbrowser_page, register_outlook

        async with _open_ixbrowser_page(self._bb, idx, proxy) as (page, context, _pid):
            fut = await install_create_account_interceptor(page)

            drive = asyncio.create_task(register_outlook(page, context, idx))
            try:
                cap = await asyncio.wait_for(asyncio.shield(fut), timeout=self._timeout)
            except asyncio.TimeoutError:
                drive.cancel()
                raise MintFailed("CreateAccount 未在超时内被截获（过不了验证码/表单失败）")

            drive.cancel()
            try:
                await drive
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

            payload = cap["payload"]
            if not payload.get("HSol"):
                raise MintFailed("截获的 CreateAccount 无 HSol token")

            cookies = await context.cookies()
            ua = await page.evaluate("() => navigator.userAgent")
            headers_in = cap["headers"]
            return MintedCredential(
                cookies=cookies,
                canary=headers_in.get("canary", ""),
                create_payload=payload,
                request_headers={
                    "canary": headers_in.get("canary", ""),
                    "hpgid": headers_in.get("hpgid", ""),
                    "scid": headers_in.get("scid", "100118"),
                },
                user_agent=ua,
                proxy=proxy,
                captured=True,
            )
