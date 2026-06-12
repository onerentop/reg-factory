from worker.flows.claude import ClaudeRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = ClaudeRegistrationFlow.__new__(ClaudeRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Prepare email", "Browser login and magic link", "Phone verification", "Extract session and cleanup",
    ]
    assert all(s.kind == "legacy" for s in steps)
