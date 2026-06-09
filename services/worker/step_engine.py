import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class StepResult:
    step_number: int
    name: str
    success: bool
    error: str | None = None
    duration_ms: int = 0
    data: dict[str, Any] | None = None


class RegistrationFlow(ABC):
    """注册流程抽象基类。模板方法——定义步骤执行的骨架算法。"""

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
    """Outlook 注册流程。"""

    def get_steps(self) -> list[str]:
        return [
            "Create email",
            "Set password",
            "Fill birthday",
            "Solve captcha",
            "Complete registration",
        ]

    async def execute_step(self, step_number: int, step_name: str, context: dict) -> StepResult:
        """Outlook 注册步骤执行。实际浏览器操作在此实现。"""
        email = context.get("email", "")

        if step_name == "Create email":
            # TODO: 接入 Playwright 填写邮箱表单
            return StepResult(step_number=step_number, name=step_name, success=True,
                            data={"email": email})

        elif step_name == "Set password":
            # TODO: 接入 Playwright 设置密码
            return StepResult(step_number=step_number, name=step_name, success=True)

        elif step_name == "Fill birthday":
            # TODO: 接入 Playwright 填写生日
            return StepResult(step_number=step_number, name=step_name, success=True)

        elif step_name == "Solve captcha":
            # TODO: 接入 Arkose Labs 验证码处理
            return StepResult(step_number=step_number, name=step_name, success=True)

        elif step_name == "Complete registration":
            # TODO: 提取 Cookie/Token 并保存
            return StepResult(step_number=step_number, name=step_name, success=True,
                            data={"status": "registered"})

        return StepResult(step_number=step_number, name=step_name, success=False,
                         error=f"Unknown step: {step_name}")


class GmailRegistrationFlow(RegistrationFlow):
    """Gmail 注册流程。"""

    def get_steps(self) -> list[str]:
        return [
            "Fill name",
            "Set birthday",
            "Choose username",
            "Set password",
            "Phone verification",
            "Accept terms",
            "Complete registration",
        ]

    async def execute_step(self, step_number: int, step_name: str, context: dict) -> StepResult:
        """Gmail 注册步骤执行。混合方案：浏览器铸 BotGuard + HTTP 手机验证。"""
        email = context.get("email", "")

        if step_name == "Fill name":
            # TODO: 接入 Playwright 或 HTTP batchexecute 填写姓名
            return StepResult(step_number=step_number, name=step_name, success=True)

        elif step_name == "Set birthday":
            # TODO: BotGuard token 铸造 + 填写生日
            return StepResult(step_number=step_number, name=step_name, success=True)

        elif step_name == "Choose username":
            # TODO: 用户名可用性检查 + 填写
            return StepResult(step_number=step_number, name=step_name, success=True,
                            data={"username": email.split("@")[0] if email else ""})

        elif step_name == "Set password":
            # TODO: 设置密码
            return StepResult(step_number=step_number, name=step_name, success=True)

        elif step_name == "Phone verification":
            # TODO: 调用 SMS Service 获取号码 + 轮询验证码
            # sms_response = await http_client.post(SMS_SERVICE_URL + "/sms/number/acquire", ...)
            # code = await http_client.get(SMS_SERVICE_URL + f"/sms/number/{order_id}/code", ...)
            return StepResult(step_number=step_number, name=step_name, success=True,
                            data={"phone_verified": True})

        elif step_name == "Accept terms":
            # TODO: 接受服务条款
            return StepResult(step_number=step_number, name=step_name, success=True)

        elif step_name == "Complete registration":
            # TODO: 完成注册 + 保存 Cookie
            return StepResult(step_number=step_number, name=step_name, success=True,
                            data={"status": "registered"})

        return StepResult(step_number=step_number, name=step_name, success=False,
                         error=f"Unknown step: {step_name}")


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
