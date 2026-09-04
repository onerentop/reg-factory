import asyncio
from worker.flows.base import (
    Step, StepResult, RegistrationFlow, FlowRegistry, LegacyBridgeStep,
)


class _FakeFlow(RegistrationFlow):
    def __init__(self, services=None):
        # 不调用 super().__init__（避免 LegacyBridge），仅本测试用。
        # 形参与 FlowRegistry.get 的 flow_cls(services) 注入契约保持一致。
        self.services = services
        self.calls = []

    def get_steps(self):
        async def s1(ctx, services):
            self.calls.append("s1"); ctx["a"] = 1
            return StepResult(success=True, data={"a": 1})

        async def s2(ctx, services):
            self.calls.append("s2")
            return StepResult(success=False, error="boom")

        async def s3(ctx, services):
            self.calls.append("s3")
            return StepResult(success=True)

        return [Step("one", s1), Step("two", s2), Step("three", s3)]


def test_run_executes_in_order_and_stops_on_failure():
    flow = _FakeFlow()
    results = asyncio.run(flow.run({}))
    assert flow.calls == ["s1", "s2"]            # s3 不执行（s2 失败短路）
    assert [r.success for r in results] == [True, False]
    assert results[0].step_number == 1 and results[0].name == "one"
    assert results[1].step_number == 2 and results[1].name == "two"
    assert results[1].error == "boom"
    assert results[0].duration_ms >= 0


def test_run_from_step_skips_earlier():
    flow = _FakeFlow()
    results = asyncio.run(flow.run({}, from_step=2))
    assert flow.calls == ["s2"]                  # s1 跳过
    assert results[0].step_number == 1 and results[0].success is True  # 跳过的记为成功占位


def test_step_exception_becomes_failed_result():
    class _Boom(RegistrationFlow):
        def __init__(self): self.services = None
        def get_steps(self):
            async def s(ctx, services): raise RuntimeError("kaboom")
            return [Step("x", s)]
    results = asyncio.run(_Boom().run({}))
    assert results[0].success is False and "kaboom" in results[0].error


def test_legacy_bridge_step_marks_kind_legacy():
    async def fn(ctx, services): return StepResult(success=True)
    step = LegacyBridgeStep("legacy-one", fn)
    assert isinstance(step, Step) and step.kind == "legacy" and step.name == "legacy-one"


def test_flow_registry_register_and_get():
    FlowRegistry.register("fake", _FakeFlow)
    flow = FlowRegistry.get("fake")
    assert isinstance(flow, _FakeFlow)


def test_flow_registry_unknown_raises():
    try:
        FlowRegistry.get("nope-platform")
        assert False, "should raise"
    except ValueError:
        pass


# ──────────────────────────────────────────────
# TaskEventEmitter
# ──────────────────────────────────────────────

def test_queue_event_emitter_wraps_payload_with_task_context():
    from worker.flows.base import QueueEventEmitter

    sent = []
    emitter = QueueEventEmitter(sent.append, "task-1", "google")
    emitter.emit("binding", {"profile_id": "777", "profile_name": "a@gmail.com"})

    assert sent == [{"type": "binding", "task_id": "task-1", "platform": "google",
                     "profile_id": "777", "profile_name": "a@gmail.com"}]


def test_flow_registry_injects_services():
    from worker.flows.base import FlowRegistry, RegistrationFlow

    class _Flow(RegistrationFlow):
        def get_steps(self): return []

    FlowRegistry.register("unit-test-platform", _Flow)
    sentinel = object()
    assert FlowRegistry.get("unit-test-platform", services=sentinel).services is sentinel


def test_flow_registry_defaults_services_to_none():
    from worker.flows.base import FlowRegistry, RegistrationFlow

    class _Flow(RegistrationFlow):
        def get_steps(self): return []

    FlowRegistry.register("unit-test-platform-2", _Flow)
    assert FlowRegistry.get("unit-test-platform-2").services is None
