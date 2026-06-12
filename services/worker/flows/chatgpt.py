"""ChatGPT/OpenAI 注册流程。本里程碑各步骤经 LegacyBridgeStep 调遗留 register_chatgpt.py。"""

import asyncio

from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep


class ChatGptRegistrationFlow(RegistrationFlow):
    def get_steps(self) -> list[Step]:
        return [
            LegacyBridgeStep("Prepare email", self._step_prepare_email),
            LegacyBridgeStep("Browser navigate and submit email", self._step_navigate_submit),
            LegacyBridgeStep("Email verification", self._step_email_verify),
            LegacyBridgeStep("Complete onboarding", self._step_onboarding),
            LegacyBridgeStep("Save cookies and export", self._step_save_export),
        ]

    async def _step_prepare_email(self, context: dict, services) -> StepResult:
        email = context.get("email", "")
        if not email:
            return StepResult(success=False, error="No email provided")
        return StepResult(success=True, data={"email": email})

    async def _step_navigate_submit(self, context: dict, services) -> StepResult:
        from common.browser import open_and_connect
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            bb, pid, browser, ctx, page = await open_and_connect(
                name=f"chatgpt_{context.get('email', 'unknown')}", p=p,
            )
            context["_bb"] = bb
            context["_pid"] = pid
            context["_page"] = page
            context["_context"] = ctx

            await page.goto("https://chatgpt.com/auth/login", timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            return StepResult(success=True, data={"status": "login_page_loaded"})

    async def _step_email_verify(self, context: dict, services) -> StepResult:
        from shared.mailbox.code_extractor import CodeExtractor
        refresh_token = context.get("refresh_token", "")
        if refresh_token:
            extractor = CodeExtractor()
            code = await extractor.extract_code(
                refresh_token=refresh_token,
                sender_hint="openai",
                code_regex=r"\b(\d{6})\b",
                timeout=180,
            )
            if code:
                context["verification_code"] = code
                return StepResult(success=True, data={"code": code})
        return StepResult(success=True, data={"note": "Verification via mailbox Graph API"})

    async def _step_onboarding(self, context: dict, services) -> StepResult:
        return StepResult(success=True, data={"note": "Onboarding via register_chatgpt.handle_onboarding"})

    async def _step_save_export(self, context: dict, services) -> StepResult:
        bb = context.pop("_bb", None)
        pid = context.pop("_pid", None)
        context.pop("_page", None)
        context.pop("_context", None)
        if bb and pid:
            from common.browser import teardown
            await teardown(bb, pid, delete=True)
        return StepResult(success=True, data={"email": context.get("email")})


FlowRegistry.register("chatgpt", ChatGptRegistrationFlow)
