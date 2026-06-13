"""Gmail 混合方案注册流程。本里程碑经 LegacyBridgeStep 调遗留 register_gmail_hybrid.py。
浏览器铸 BotGuard token（姓名→生日→用户名→密码）+ 浏览器手机验证。"""

import asyncio
import random
import string

from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep


class GmailRegistrationFlow(RegistrationFlow):
    def get_steps(self) -> list[Step]:
        return [
            LegacyBridgeStep("Generate profile", self._step_generate_profile),
            LegacyBridgeStep("Browser drive to phone", self._step_drive_to_phone),
            LegacyBridgeStep("Phone verification", self._step_phone_verify),
            LegacyBridgeStep("Save and cleanup", self._step_save_cleanup),
        ]

    async def _step_generate_profile(self, context: dict, services) -> StepResult:
        first = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 8))).capitalize()
        last = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 8))).capitalize()
        password = f"Gm{''.join(random.choices(string.ascii_letters + string.digits, k=6))}!{random.randint(10, 99)}"
        context["profile"] = {
            "first": first, "last": last, "pw": password,
            "year": random.randint(1988, 1998),
            "month": random.randint(1, 12),
            "day": random.randint(1, 28),
        }
        return StepResult(success=True, data={"first": first, "last": last})

    async def _step_drive_to_phone(self, context: dict, services) -> StepResult:
        from common.browser import open_and_connect
        from register_gmail_hybrid import drive_to_phone, build_signup_url
        from playwright.async_api import async_playwright
        # 不能用 `async with async_playwright()`：它会在本 step return 时 stop() driver，
        # 导致后续 _step_phone_verify 拿到的 page 失效（Target page/browser has been closed）。
        # 改为手动 start() 并存入 context，跨 step 保活，由 _step_save_cleanup 统一 stop()。
        p = await async_playwright().start()
        context["_pw"] = p
        bb, pid, browser, ctx, page = await open_and_connect(
            name=f"gmail_{context.get('profile', {}).get('first', 'unknown')}", p=p,
            proxy_str=context.get("proxy", ""),
        )
        context["_bb"] = bb
        context["_pid"] = pid
        context["_page"] = page
        context["_context"] = ctx
        signup_url = build_signup_url()
        await page.goto(signup_url, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        profile = context.get("profile", {})
        success = await drive_to_phone(page, profile)
        context["profile"] = profile
        if success:
            return StepResult(success=True, data={"username": profile.get("username", "")})
        return StepResult(success=False, error="Failed to drive to phone verification page")

    async def _step_phone_verify(self, context: dict, services) -> StepResult:
        page = context.get("_page")
        ctx = context.get("_context")
        profile = context.get("profile", {})
        if not page:
            return StepResult(success=False, error="No browser session available")
        from register_gmail_hybrid import browser_phone_and_finalize
        pid = context.get("_pid")
        result = await browser_phone_and_finalize(page, profile, ctx=ctx, profile_id=pid,
                                                  sms_config=context.get("sms"))
        if result and result.get("email"):
            context["email"] = result["email"]
            context["password"] = profile.get("pw", "")
            context["result"] = result
            return StepResult(success=True, data={"email": result["email"]})
        return StepResult(success=False, error=f"Phone verification failed: {result}")

    async def _step_save_cleanup(self, context: dict, services) -> StepResult:
        bb = context.pop("_bb", None)
        pid = context.pop("_pid", None)
        context.pop("_page", None)
        context.pop("_context", None)
        email = context.get("email")
        if bb and pid:
            if email:
                # 成功建号：保留窗口（不删 profile），仅关闭；窗口改名=邮箱、备注=密码|手机，便于识别。
                try:
                    bb.close_browser(pid)
                except Exception:
                    pass
                try:
                    from ixbrowser_local_api.entities import Profile as _IxProfile
                    up = _IxProfile()
                    up.profile_id = int(pid)
                    up.name = email
                    _res = context.get("result", {}) or {}
                    up.note = f"{context.get('password', '')} | {_res.get('phone', '')}"
                    bb._call("update_profile", up)
                except Exception:
                    pass
            else:
                # 失败：删除窗口释放 ixBrowser 配额
                from common.browser import teardown
                await teardown(bb, pid, delete=True)
        pw = context.pop("_pw", None)
        if pw:
            try:
                await pw.stop()
            except Exception:
                pass
        return StepResult(success=True, data={
            "email": context.get("email"),
            "password": context.get("password"),
            "username": context.get("profile", {}).get("username"),
        })


FlowRegistry.register("google", GmailRegistrationFlow)
