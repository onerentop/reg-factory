"""浏览器侧：过 PerimeterX → 让 Arkose JS 铸 HSol → 路由拦截截获 CreateAccount → abort（不建号）。"""

import asyncio
import json

from .credential import MintedCredential
from .errors import MintFailed


async def install_create_account_interceptor(page):
    """在 page 上挂 CreateAccount 路由拦截器（await 确保注册完成，避免与导航竞态）。

    Outlook 会发两次 CreateAccount：第一次**无 HSol**（触发验证码挑战），过码后第二次
    **带 HSol**。只截获并 abort 带 HSol 的那次；无 HSol 的放行(continue)，让验证码流程正常走。
    返回一个 asyncio.Future，截获到带 HSol 的请求时 set_result {"payload", "headers"}。
    """
    fut: asyncio.Future = asyncio.get_running_loop().create_future()

    async def _intercept(route):
        req = route.request
        try:
            payload = json.loads(req.post_data or "{}")
        except Exception:
            payload = {}
        if payload.get("HSol"):
            if not fut.done():
                fut.set_result({"payload": payload, "headers": dict(req.headers)})
            try:
                await route.abort()
            except Exception:
                pass
        else:
            # 无 HSol 的首次提交：放行，让服务端返回验证码挑战、页面正常走过码流程
            try:
                await route.continue_()
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
                # 消化已取消任务的异常，避免 "Task exception was never retrieved" 警告
                drive.add_done_callback(
                    lambda t: t.cancelled() or t.exception())
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

            headers_in = cap["headers"]
            # UA 从截获的请求头取——abort 后页面可能已跳转，page.evaluate 会因
            # "Execution context was destroyed" 抛错；CreateAccount 请求头里本就带 UA。
            ua = headers_in.get("user-agent", "")
            try:
                cookies = await context.cookies()
            except Exception:
                cookies = []
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
