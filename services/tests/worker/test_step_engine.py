import pytest
from worker.step_engine import (
    FlowRegistry, OutlookRegistrationFlow, GmailRegistrationFlow,
    ClaudeRegistrationFlow, ChatGptRegistrationFlow, GrokRegistrationFlow,
    StepResult,
)


def test_outlook_steps():
    flow = OutlookRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 2
    assert "Generate credentials" in [s.name for s in steps]
    assert "Browser registration with proxy" in [s.name for s in steps]


def test_gmail_steps():
    flow = GmailRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 4
    assert "Generate profile" in [s.name for s in steps]
    assert "Phone verification" in [s.name for s in steps]


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
    step = flow.get_steps()[0]
    result = await step.run(context, None)
    assert result.success is True
    assert "email" in context
    assert "password" in context
    assert "@" in context["email"]


@pytest.mark.asyncio
async def test_gmail_generate_profile():
    """测试第一步可以独立执行"""
    flow = GmailRegistrationFlow()
    context = {}
    step = flow.get_steps()[0]
    result = await step.run(context, None)
    assert result.success is True
    assert "profile" in context
    assert "first" in context["profile"]
    assert "pw" in context["profile"]


def test_claude_steps():
    flow = ClaudeRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 4
    assert "magic link" in steps[1].name.lower()


def test_chatgpt_steps():
    flow = ChatGptRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 5
    assert "onboarding" in steps[3].name.lower()


def test_grok_steps():
    flow = GrokRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 5
    assert "Turnstile" in steps[1].name


def test_all_platforms_registered():
    for platform in ["outlook", "google", "claude", "chatgpt", "grok"]:
        flow = FlowRegistry.get(platform)
        assert flow is not None
        assert len(flow.get_steps()) >= 2
