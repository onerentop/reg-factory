from worker.flows.base import (
    Step, StepFn, StepResult, RegistrationFlow, FlowRegistry, LegacyBridgeStep,
)

# import 受支持平台模块 → 触发模块底部的 FlowRegistry.register(...)
from worker.flows import outlook, gmail  # noqa: E402,F401

__all__ = ["Step", "StepFn", "StepResult", "RegistrationFlow", "FlowRegistry", "LegacyBridgeStep"]
