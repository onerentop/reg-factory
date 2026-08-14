import pytest

from worker.step_engine import FlowRegistry, GmailRegistrationFlow, OutlookRegistrationFlow


def test_outlook_steps():
    flow = OutlookRegistrationFlow()
    assert [step.name for step in flow.get_steps()] == [
        "Generate credentials",
        "Browser registration with proxy",
    ]


def test_gmail_steps():
    flow = GmailRegistrationFlow()
    assert [step.name for step in flow.get_steps()] == [
        "Generate profile",
        "Browser drive to phone",
        "Phone verification",
        "Save and cleanup",
    ]


def test_flow_registry_only_supports_outlook_and_google():
    assert isinstance(FlowRegistry.get("outlook"), OutlookRegistrationFlow)
    assert isinstance(FlowRegistry.get("google"), GmailRegistrationFlow)
    for removed in ("claude", "chatgpt", "grok"):
        with pytest.raises(ValueError, match="Unknown platform"):
            FlowRegistry.get(removed)


@pytest.mark.asyncio
async def test_outlook_generate_credentials():
    flow = OutlookRegistrationFlow()
    context = {}
    result = await flow.get_steps()[0].run(context, None)
    assert result.success is True
    assert "@" in context["email"]
    assert context["password"]


@pytest.mark.asyncio
async def test_gmail_generate_profile():
    flow = GmailRegistrationFlow()
    context = {}
    result = await flow.get_steps()[0].run(context, None)
    assert result.success is True
    assert context["profile"]["first"]
    assert context["profile"]["pw"]
