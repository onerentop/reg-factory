"""Outlook 浏览器注册流程。本里程碑各步骤经 LegacyBridgeStep 调遗留 register_outlook_standalone.py。"""

from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep


class OutlookRegistrationFlow(RegistrationFlow):
    def get_steps(self) -> list[Step]:
        return [
            LegacyBridgeStep("Generate credentials", self._step_generate),
            LegacyBridgeStep("Browser registration with proxy", self._step_register),
        ]

    async def _step_generate(self, context: dict, services) -> StepResult:
        from register_outlook_standalone import (
            generate_email_password, generate_birthday, generate_name,
        )
        email, password, _prefix = generate_email_password()
        first, last = generate_name()
        birthday = generate_birthday()
        context["email"] = email
        context["password"] = password
        context["first_name"] = first
        context["last_name"] = last
        context["birthday"] = birthday
        return StepResult(success=True, data={"email": email, "first_name": first, "last_name": last})

    async def _step_register(self, context: dict, services) -> StepResult:
        proxy_str = context.get("proxy", "")
        idx = context.get("idx", 0)
        mode = context.get("mode", "browser")
        email = password = graph_token = None

        if mode == "protocol":
            from register_outlook_standalone import register_outlook_protocol
            result = register_outlook_protocol(proxy_str, idx)
            if result and result[0]:
                email, password = result[0], result[1]
        else:  # browser（默认）
            from common.browser_provider import get_browser_provider
            from register_outlook_standalone import _register_one_browser
            bb = get_browser_provider()
            result = await _register_one_browser(bb, idx, proxy_str)
            if result and len(result) >= 2 and result[0]:
                email, password = result[0], result[1]
                graph_token = result[2] if len(result) > 2 else None

        if email:
            context["email"] = email
            context["password"] = password
            if graph_token:
                context["refresh_token"] = graph_token
            return StepResult(success=True, data={"email": email, "has_token": bool(graph_token), "mode": mode})

        return StepResult(success=False, error=f"Registration failed (mode={mode}) — check ixBrowser/proxy/captcha")


FlowRegistry.register("outlook", OutlookRegistrationFlow)
