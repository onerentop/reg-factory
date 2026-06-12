from worker.flows.grok import GrokRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = GrokRegistrationFlow.__new__(GrokRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Prepare email and proxy", "Browser navigate with Turnstile", "Email verification",
        "Complete registration", "Save cookies and upload",
    ]
    assert all(s.kind == "legacy" for s in steps)
