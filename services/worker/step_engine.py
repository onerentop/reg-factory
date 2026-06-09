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
        return StepResult(step_number=step_number, name=step_name, success=True)


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
        return StepResult(step_number=step_number, name=step_name, success=True)


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
