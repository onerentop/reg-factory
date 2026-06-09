import pytest
from worker.step_engine import (
    FlowRegistry, OutlookRegistrationFlow, GmailRegistrationFlow, StepResult,
)


def test_outlook_steps():
    flow = OutlookRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 5
    assert "Create email" in steps


def test_gmail_steps():
    flow = GmailRegistrationFlow()
    steps = flow.get_steps()
    assert len(steps) == 7
    assert "Phone verification" in steps


@pytest.mark.asyncio
async def test_run_flow():
    flow = OutlookRegistrationFlow()
    results = await flow.run(context={"email": "test@test.com"})
    assert len(results) == 5
    assert all(r.success for r in results)


@pytest.mark.asyncio
async def test_run_flow_from_step():
    flow = GmailRegistrationFlow()
    results = await flow.run(context={}, from_step=3)
    assert len(results) == 7
    assert results[0].step_number == 1
    assert results[0].duration_ms == 0
    assert results[2].step_number == 3


def test_flow_registry():
    flow = FlowRegistry.get("outlook")
    assert isinstance(flow, OutlookRegistrationFlow)

    flow2 = FlowRegistry.get("google")
    assert isinstance(flow2, GmailRegistrationFlow)


def test_flow_registry_unknown():
    with pytest.raises(ValueError, match="Unknown platform"):
        FlowRegistry.get("nonexistent")
