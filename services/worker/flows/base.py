"""注册流程地基：Step 对象化契约 + 模板方法 + 注册表 + 遗留桥接 Step。"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# Step 可调用签名：(context, services) -> StepResult
StepFn = Callable[[dict, Any], Awaitable["StepResult"]]


@dataclass
class StepResult:
    success: bool
    name: str = ""
    step_number: int = 0
    error: str | None = None
    duration_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """一个注册步骤：name + 可调用 run(context, services) -> StepResult。
    kind 用于迁移可观测性：'native'(原生共享服务) / 'legacy'(桥接遗留单体)。"""
    name: str
    run: StepFn
    kind: str = "native"


def LegacyBridgeStep(name: str, run: StepFn) -> Step:
    """工厂：包装遗留调用的 Step（kind='legacy'）。Strangler 迁移时整体替换为 native Step。"""
    return Step(name=name, run=run, kind="legacy")


class TaskEventEmitter(ABC):
    """子进程向父进程回传事件的契约。子进程不写库，一切经父进程落库。"""

    @abstractmethod
    def emit(self, event_type: str, data: dict) -> None:
        ...


class QueueEventEmitter(TaskEventEmitter):
    """把事件塞进 multiprocessing.Queue，由父进程 _handle_event 落库。"""

    def __init__(self, emit: Callable[[dict], None], task_id: str, platform: str):
        self._emit = emit
        self._task_id = task_id
        self._platform = platform

    def emit(self, event_type: str, data: dict) -> None:
        self._emit({"type": event_type, "task_id": self._task_id,
                    "platform": self._platform, **data})


class RegistrationFlow(ABC):
    """注册流程抽象基类。模板方法 run() 定义步骤执行骨架。

    services: 注入的 ServiceBundle（本里程碑各平台仍走 LegacyBridgeStep，可为 None）。
    """

    def __init__(self, services: Any = None):
        self.services = services
        # 让桥接的遗留 import 可用
        from worker.legacy_bridge import LegacyBridge
        self._bridge = LegacyBridge()
        self._bridge.ensure_importable()

    @abstractmethod
    def get_steps(self) -> list[Step]:
        ...

    async def run(self, context: dict, from_step: int = 1) -> list[StepResult]:
        steps = self.get_steps()
        results: list[StepResult] = []
        for i, step in enumerate(steps, 1):
            if i < from_step:
                results.append(StepResult(success=True, name=step.name, step_number=i, duration_ms=0))
                continue
            start = time.monotonic()
            try:
                result = await step.run(context, self.services)
                result.step_number = i
                result.name = step.name
                result.duration_ms = int((time.monotonic() - start) * 1000)
                results.append(result)
                if not result.success:
                    break
            except Exception as e:
                results.append(StepResult(
                    success=False, name=step.name, step_number=i,
                    error=str(e), duration_ms=int((time.monotonic() - start) * 1000),
                ))
                break
        return results


class FlowRegistry:
    """注册流程注册表。工厂模式。各平台模块 import 时调用 register() 登记自己。"""

    _flows: dict[str, type[RegistrationFlow]] = {}

    @classmethod
    def get(cls, platform: str, services: Any = None) -> RegistrationFlow:
        flow_cls = cls._flows.get(platform)
        if flow_cls is None:
            raise ValueError(f"Unknown platform: {platform}")
        return flow_cls(services)

    @classmethod
    def register(cls, platform: str, flow_cls: type[RegistrationFlow]) -> None:
        cls._flows[platform] = flow_cls
