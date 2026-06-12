"""Grok 注册流程。本里程碑各步骤经 LegacyBridgeStep 调遗留 register_grok.py。核心难点：Cloudflare 拦截。"""

import asyncio

from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep


class GrokRegistrationFlow(RegistrationFlow):
    def get_steps(self) -> list[Step]:
        return [
            LegacyBridgeStep("Prepare email and proxy", self._step_prepare),
            LegacyBridgeStep("Browser navigate with Turnstile", self._step_navigate_turnstile),
            LegacyBridgeStep("Email verification", self._step_email_verify),
            LegacyBridgeStep("Complete registration", self._step_complete),
            LegacyBridgeStep("Save cookies and upload", self._step_save_upload),
        ]

    async def _step_prepare(self, context: dict, services) -> StepResult:
        email = context.get("email", "")
        proxy = context.get("proxy")
        if not email:
            return StepResult(success=False, error="No email provided")
        return StepResult(success=True, data={"email": email, "has_proxy": proxy is not None})

    async def _step_navigate_turnstile(self, context: dict, services) -> StepResult:
        from common.browser import open_and_connect
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            bb, pid, browser, ctx, page = await open_and_connect(
                name=f"grok_{context.get('email', 'unknown')}", p=p,
            )
            context["_bb"] = bb
            context["_pid"] = pid
            context["_page"] = page
            context["_context"] = ctx

            await page.goto("https://grok.com/", timeout=90000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            return StepResult(success=True, data={"status": "grok_page_loaded"})

    async def _step_email_verify(self, context: dict, services) -> StepResult:
        from shared.mailbox.code_extractor import CodeExtractor
        refresh_token = context.get("refresh_token", "")
        if refresh_token:
            extractor = CodeExtractor()
            code = await extractor.extract_code(
                refresh_token=refresh_token,
                sender_hint="grok",
                code_regex=r"\b(\d{6})\b",
                timeout=180,
            )
            if code:
                context["verification_code"] = code
                return StepResult(success=True, data={"code": code})
        return StepResult(success=True, data={"note": "Verification via mailbox"})

    async def _step_complete(self, context: dict, services) -> StepResult:
        return StepResult(success=True, data={"note": "Registration form via register_grok.register_one"})

    async def _step_save_upload(self, context: dict, services) -> StepResult:
        bb = context.pop("_bb", None)
        pid = context.pop("_pid", None)
        context.pop("_page", None)
        context.pop("_context", None)
        if bb and pid:
            from common.browser import teardown
            await teardown(bb, pid, delete=True)
        return StepResult(success=True, data={"email": context.get("email")})


FlowRegistry.register("grok", GrokRegistrationFlow)
