import pytest

import worker.flows  # 触发受支持平台注册
from worker.flows import FlowRegistry
from worker.flows.outlook import OutlookRegistrationFlow
from worker.step_engine import FlowRegistry as LegacyRegistry, OutlookRegistrationFlow as LegacyOutlook


@pytest.mark.parametrize("platform,cls_name", [
    ("outlook", "OutlookRegistrationFlow"),
    ("google", "GmailRegistrationFlow"),
])
def test_registry_resolves_supported_platforms(platform, cls_name):
    flow = FlowRegistry.get(platform)
    assert type(flow).__name__ == cls_name


@pytest.mark.parametrize("platform", ["claude", "chatgpt", "grok"])
def test_registry_rejects_removed_platforms(platform):
    with pytest.raises(ValueError, match="Unknown platform"):
        FlowRegistry.get(platform)


def test_backcompat_step_engine_reexports():
    assert LegacyRegistry is FlowRegistry
    assert LegacyOutlook is OutlookRegistrationFlow
