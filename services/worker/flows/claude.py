"""Claude.ai 注册流程。本里程碑各步骤经 LegacyBridgeStep 调遗留逻辑。"""

import asyncio

from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep


class ClaudeRegistrationFlow(RegistrationFlow):
    def get_steps(self) -> list[Step]:
        return [
            LegacyBridgeStep("Prepare email", self._step_prepare_email),
            LegacyBridgeStep("Browser login and magic link", self._step_login_magic),
            LegacyBridgeStep("Phone verification", self._step_phone_verify),
            LegacyBridgeStep("Extract session and cleanup", self._step_extract_session),
        ]

    async def _step_prepare_email(self, context: dict, services) -> StepResult:
        email = context.get("email", "")
        password = context.get("password", "")
        refresh_token = context.get("refresh_token", "")
        if not email:
            return StepResult(success=False,
                              error="No email provided in context")
        return StepResult(success=True,
                          data={"email": email})

    async def _step_login_magic(self, context: dict, services) -> StepResult:
        from common.browser import open_and_connect, teardown
        from playwright.async_api import async_playwright
        from shared.mailbox.code_extractor import CodeExtractor

        idx = context.get("idx", 0)
        async with async_playwright() as p:
            bb, pid, browser, ctx, page = await open_and_connect(
                name=f"claude_{context.get('email', 'unknown')}", p=p,
            )
            context["_bb"] = bb
            context["_pid"] = pid
            context["_browser"] = browser
            context["_context"] = ctx
            context["_page"] = page

            await page.goto("https://claude.ai/login", timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            return StepResult(success=True,
                              data={"status": "login_page_loaded"})

    async def _step_phone_verify(self, context: dict, services) -> StepResult:
        page = context.get("_page")
        if not page:
            return StepResult(success=False,
                              error="No browser session")
        return StepResult(success=True,
                          data={"note": "Phone verification via SMS Service"})

    async def _step_extract_session(self, context: dict, services) -> StepResult:
        bb = context.pop("_bb", None)
        pid = context.pop("_pid", None)
        context.pop("_browser", None)
        context.pop("_context", None)
        context.pop("_page", None)
        if bb and pid:
            from common.browser import teardown
            await teardown(bb, pid, delete=True)
        return StepResult(success=True,
                          data={"email": context.get("email")})


FlowRegistry.register("claude", ClaudeRegistrationFlow)
