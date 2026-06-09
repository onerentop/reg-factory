from shared.audit import AuditRecorder, audited


def test_recorder_records():
    recorder = AuditRecorder()
    recorder.record("admin", "delete", "account-123")
    assert len(recorder.records) == 1
    assert recorder.records[0]["action"] == "delete"


def test_recorder_callback():
    events = []
    recorder = AuditRecorder()
    recorder.add_callback(lambda e: events.append(e))
    recorder.record("user1", "update", "config-key")
    assert len(events) == 1
    assert events[0]["operator"] == "user1"


def test_recorder_clear():
    recorder = AuditRecorder()
    recorder.record("a", "b")
    recorder.clear()
    assert len(recorder.records) == 0
