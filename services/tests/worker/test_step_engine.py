import pytest
from worker.step_engine import (
    FlowRegistry, OutlookRegistrationFlow, GmailRegistrationFlow, StepResult,
)


def test_outlook_steps():
    flow = OutlookRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 4
    assert "Generate credentials" in steps
    assert "Browser registration" in steps


def test_gmail_steps():
    flow = GmailRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 4
    assert "Generate profile" in steps
    assert "Phone verification" in steps


def test_flow_registry():
    flow = FlowRegistry.get("outlook")
    assert isinstance(flow, OutlookRegistrationFlow)
    flow2 = FlowRegistry.get("google")
    assert isinstance(flow2, GmailRegistrationFlow)


def test_flow_registry_unknown():
    with pytest.raises(ValueError, match="Unknown platform"):
        FlowRegistry.get("nonexistent")


@pytest.mark.asyncio
async def test_outlook_generate_credentials():
    """测试第一步可以独立执行（不需要浏览器）"""
    flow = OutlookRegistrationFlow()
    context = {}
    result = await flow.execute_step(1, "Generate credentials", context)
    assert result.success is True
    assert "email" in context
    assert "password" in context
    assert "@" in context["email"]


@pytest.mark.asyncio
async def test_gmail_generate_profile():
    """测试第一步可以独立执行"""
    flow = GmailRegistrationFlow()
    context = {}
    result = await flow.execute_step(1, "Generate profile", context)
    assert result.success is True
    assert "profile" in context
    assert "first" in context["profile"]
    assert "pw" in context["profile"]
