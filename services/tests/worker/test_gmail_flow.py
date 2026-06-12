from worker.flows.gmail import GmailRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = GmailRegistrationFlow.__new__(GmailRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Generate profile", "Browser drive to phone", "Phone verification", "Save and cleanup",
    ]
    assert all(s.kind == "legacy" for s in steps)
