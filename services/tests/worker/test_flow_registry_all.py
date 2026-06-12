import worker.flows  # 触发各平台注册
from worker.flows import FlowRegistry
from worker.flows.outlook import OutlookRegistrationFlow
# 向后兼容：旧路径仍可用
from worker.step_engine import FlowRegistry as LegacyRegistry, OutlookRegistrationFlow as LegacyOutlook
import pytest


@pytest.mark.parametrize("platform,cls_name", [
    ("outlook", "OutlookRegistrationFlow"),
    ("google", "GmailRegistrationFlow"),
    ("claude", "ClaudeRegistrationFlow"),
    ("chatgpt", "ChatGptRegistrationFlow"),
    ("grok", "GrokRegistrationFlow"),
])
def test_registry_resolves_all_platforms(platform, cls_name):
    flow = FlowRegistry.get(platform)
    assert type(flow).__name__ == cls_name


def test_backcompat_step_engine_reexports():
    assert LegacyRegistry is FlowRegistry
    assert LegacyOutlook is OutlookRegistrationFlow
