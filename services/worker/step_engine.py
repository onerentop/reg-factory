"""向后兼容壳：原 step_engine 内容已拆分到 worker.flows。保留此模块供旧 import 路径。"""

from worker.flows import (  # noqa: F401
    Step, StepFn, StepResult, RegistrationFlow, FlowRegistry, LegacyBridgeStep,
)
from worker.flows.outlook import OutlookRegistrationFlow  # noqa: F401
from worker.flows.gmail import GmailRegistrationFlow  # noqa: F401
from worker.flows.claude import ClaudeRegistrationFlow  # noqa: F401
from worker.flows.chatgpt import ChatGptRegistrationFlow  # noqa: F401
from worker.flows.grok import GrokRegistrationFlow  # noqa: F401
