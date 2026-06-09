"""注册流程步骤引擎。模板方法模式 + LegacyBridge 适配现有脚本。"""

import time
import asyncio
import random
import string
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from worker.legacy_bridge import LegacyBridge


@dataclass
class StepResult:
    step_number: int
    name: str
    success: bool
    error: str | None = None
    duration_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)


class RegistrationFlow(ABC):
    """注册流程抽象基类。模板方法——定义步骤执行的骨架算法。"""

    def __init__(self):
        self._bridge = LegacyBridge()
        self._bridge.ensure_importable()

    @abstractmethod
    def get_steps(self) -> list[str]:
        ...

    @abstractmethod
    async def execute_step(self, step_number: int, step_name: str, context: dict) -> StepResult:
        ...

    async def run(self, context: dict, from_step: int = 1) -> list[StepResult]:
        steps = self.get_steps()
        results = []
        for i, name in enumerate(steps, 1):
            if i < from_step:
                results.append(StepResult(step_number=i, name=name, success=True, duration_ms=0))
                continue
            start = time.monotonic()
            try:
                result = await self.execute_step(i, name, context)
                result.duration_ms = int((time.monotonic() - start) * 1000)
                results.append(result)
                if not result.success:
                    break
            except Exception as e:
                duration = int((time.monotonic() - start) * 1000)
                results.append(StepResult(
                    step_number=i, name=name, success=False,
                    error=str(e), duration_ms=duration,
                ))
                break
        return results


class OutlookRegistrationFlow(RegistrationFlow):
    """Outlook 浏览器注册流程。通过 LegacyBridge 调用 register_outlook_standalone.py。"""

    def get_steps(self) -> list[str]:
        return [
            "Generate credentials",
            "Browser registration",
            "Extract Graph Token",
            "Save and cleanup",
        ]

    async def execute_step(self, step_number: int, step_name: str, context: dict) -> StepResult:

        if step_name == "Generate credentials":
            from register_outlook_standalone import generate_email_password, generate_birthday, generate_name
            email, password, _prefix = generate_email_password()
            first, last = generate_name()
            birthday = generate_birthday()
            context["email"] = email
            context["password"] = password
            context["first_name"] = first
            context["last_name"] = last
            context["birthday"] = birthday
            return StepResult(
                step_number=step_number, name=step_name, success=True,
                data={"email": email, "first_name": first, "last_name": last},
            )

        elif step_name == "Browser registration":
            from common.browser import open_and_connect
            from register_outlook_standalone import register_outlook
            from playwright.async_api import async_playwright

            proxy_str = context.get("proxy")
            idx = context.get("idx", 0)

            async with async_playwright() as p:
                bb, pid, browser, ctx, page = await open_and_connect(
                    name=f"outlook_{context.get('email', 'unknown')}", p=p,
                )
                context["_bb"] = bb
                context["_pid"] = pid
                context["_browser"] = browser
                context["_context"] = ctx
                context["_page"] = page

                result = await register_outlook(page, ctx, idx=idx)
                if isinstance(result, tuple):
                    reg_email, reg_password = result
                    if reg_email:
                        context["email"] = reg_email
                        context["password"] = reg_password
                        return StepResult(
                            step_number=step_number, name=step_name, success=True,
                            data={"email": reg_email},
                        )

                return StepResult(
                    step_number=step_number, name=step_name, success=False,
                    error="Registration failed",
                )

        elif step_name == "Extract Graph Token":
            page = context.get("_page")
            ctx = context.get("_context")
            email = context.get("email", "")
            password = context.get("password", "")

            if not page or not ctx:
                return StepResult(
                    step_number=step_number, name=step_name, success=False,
                    error="No browser session available",
                )

            from register_outlook_standalone import extract_graph_token
            token = await extract_graph_token(page, ctx, email, password)
            if token:
                context["refresh_token"] = token
                return StepResult(
                    step_number=step_number, name=step_name, success=True,
                    data={"has_token": True},
                )
            return StepResult(
                step_number=step_number, name=step_name, success=True,
                data={"has_token": False, "note": "Token extraction skipped or failed"},
            )

        elif step_name == "Save and cleanup":
            bb = context.pop("_bb", None)
            pid = context.pop("_pid", None)
            context.pop("_browser", None)
            context.pop("_context", None)
            context.pop("_page", None)

            if bb and pid:
                from common.browser import teardown
                await teardown(bb, pid, delete=True)

            return StepResult(
                step_number=step_number, name=step_name, success=True,
                data={
                    "email": context.get("email"),
                    "password": context.get("password"),
                    "refresh_token": context.get("refresh_token"),
                },
            )

        return StepResult(
            step_number=step_number, name=step_name, success=False,
            error=f"Unknown step: {step_name}",
        )


class GmailRegistrationFlow(RegistrationFlow):
    """Gmail 混合方案注册流程。通过 LegacyBridge 调用 register_gmail_hybrid.py。

    浏览器铸 BotGuard token（姓名→生日→用户名→密码）+ 浏览器手机验证。
    """

    def get_steps(self) -> list[str]:
        return [
            "Generate profile",
            "Browser drive to phone",
            "Phone verification",
            "Save and cleanup",
        ]

    async def execute_step(self, step_number: int, step_name: str, context: dict) -> StepResult:

        if step_name == "Generate profile":
            first = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 8))).capitalize()
            last = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 8))).capitalize()
            password = f"Gm{''.join(random.choices(string.ascii_letters + string.digits, k=6))}!{random.randint(10, 99)}"

            context["profile"] = {
                "first": first, "last": last, "pw": password,
                "year": random.randint(1988, 1998),
                "month": random.randint(1, 12),
                "day": random.randint(1, 28),
            }
            return StepResult(
                step_number=step_number, name=step_name, success=True,
                data={"first": first, "last": last},
            )

        elif step_name == "Browser drive to phone":
            from common.browser import open_and_connect
            from register_gmail_hybrid import drive_to_phone, build_signup_url
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                bb, pid, browser, ctx, page = await open_and_connect(
                    name=f"gmail_{context.get('profile', {}).get('first', 'unknown')}", p=p,
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
                    return StepResult(
                        step_number=step_number, name=step_name, success=True,
                        data={"username": profile.get("username", "")},
                    )
                return StepResult(
                    step_number=step_number, name=step_name, success=False,
                    error="Failed to drive to phone verification page",
                )

        elif step_name == "Phone verification":
            page = context.get("_page")
            ctx = context.get("_context")
            profile = context.get("profile", {})

            if not page:
                return StepResult(
                    step_number=step_number, name=step_name, success=False,
                    error="No browser session available",
                )

            from register_gmail_hybrid import browser_phone_and_finalize
            pid = context.get("_pid")
            result = await browser_phone_and_finalize(page, profile, ctx=ctx, profile_id=pid)

            if result and result.get("email"):
                context["email"] = result["email"]
                context["password"] = profile.get("pw", "")
                context["result"] = result
                return StepResult(
                    step_number=step_number, name=step_name, success=True,
                    data={"email": result["email"]},
                )
            return StepResult(
                step_number=step_number, name=step_name, success=False,
                error=f"Phone verification failed: {result}",
            )

        elif step_name == "Save and cleanup":
            bb = context.pop("_bb", None)
            pid = context.pop("_pid", None)
            context.pop("_page", None)
            context.pop("_context", None)

            if bb and pid:
                from common.browser import teardown
                await teardown(bb, pid, delete=True)

            return StepResult(
                step_number=step_number, name=step_name, success=True,
                data={
                    "email": context.get("email"),
                    "password": context.get("password"),
                    "username": context.get("profile", {}).get("username"),
                },
            )

        return StepResult(
            step_number=step_number, name=step_name, success=False,
            error=f"Unknown step: {step_name}",
        )


class FlowRegistry:
    """注册流程注册表。工厂模式。"""

    _flows: dict[str, type[RegistrationFlow]] = {
        "outlook": OutlookRegistrationFlow,
        "google": GmailRegistrationFlow,
    }

    @classmethod
    def get(cls, platform: str) -> RegistrationFlow:
        flow_cls = cls._flows.get(platform)
        if flow_cls is None:
            raise ValueError(f"Unknown platform: {platform}")
        return flow_cls()

    @classmethod
    def register(cls, platform: str, flow_cls: type[RegistrationFlow]) -> None:
        cls._flows[platform] = flow_cls
