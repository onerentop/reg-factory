from worker.flows.chatgpt import ChatGptRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = ChatGptRegistrationFlow.__new__(ChatGptRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Prepare email", "Browser navigate and submit email", "Email verification",
        "Complete onboarding", "Save cookies and export",
    ]
    assert all(s.kind == "legacy" for s in steps)
