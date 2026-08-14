import pytest

from gateway.registration_jobs import RegistrationJobService, serialize_event, serialize_job


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value if isinstance(self._value, list) else []


class FakeSession:
    def __init__(self):
        self.job = None
        self.events = []

    async def execute(self, statement):
        description = str(statement)
        if "task_events" in description:
            after = 0
            for criterion in statement._where_criteria:
                right = getattr(criterion, "right", None)
                value = getattr(right, "value", None)
                if isinstance(value, int):
                    after = value
            return FakeResult([event for event in self.events if event.seq > after])
        return FakeResult(self.job)

    def add(self, model):
        if model.__class__.__name__ == "RegistrationJob":
            self.job = model
        else:
            self.events.append(model)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_registration_job_is_created_once_and_updated():
    session = FakeSession()
    service = RegistrationJobService(session)

    queued = await service.enqueue("task-001", "outlook")
    updated = await service.update(
        "task-001",
        platform="outlook",
        status="succeeded",
        result={"success": True},
    )

    assert queued is updated
    assert updated.status == "succeeded"
    assert serialize_job(updated)["result"] == {"success": True}



@pytest.mark.asyncio
async def test_task_events_are_sequenced_and_project_terminal_status():
    session = FakeSession()
    service = RegistrationJobService(session)

    first = await service.append_event(
        "task-001",
        platform="outlook",
        event_type="status",
        status="running",
    )
    second = await service.append_event(
        "task-001",
        platform="outlook",
        event_type="log",
        status="running",
        message="browser opened",
        level="INFO",
    )
    terminal = await service.append_event(
        "task-001",
        platform="outlook",
        event_type="result",
        status="succeeded",
        result={"success": True},
        data={"success": True},
    )

    assert [event.seq for event in session.events] == [1, 2, 3]
    assert [first.event_type, second.event_type, terminal.event_type] == [
        "status",
        "log",
        "result",
    ]
    assert session.job.status == "succeeded"
    assert session.job.last_event_seq == 3
    assert serialize_event(second)["message"] == "browser opened"



@pytest.mark.asyncio
async def test_task_events_can_resume_after_a_sequence_cursor():
    session = FakeSession()
    service = RegistrationJobService(session)
    for status in ("queued", "starting", "running"):
        await service.append_event(
            "task-001", platform="outlook", event_type="status", status=status
        )

    events, has_more = await service.list_events("task-001", after=1, limit=10)

    assert [event.seq for event in events] == [2, 3]
    assert has_more is False
