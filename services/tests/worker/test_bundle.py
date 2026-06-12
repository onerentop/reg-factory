from worker.capabilities.bundle import ServiceBundle


def test_bundle_all_optional_defaults_none():
    b = ServiceBundle()
    assert b.browser is None and b.proxy is None and b.captcha is None
    assert b.emails is None and b.sms is None and b.tokens is None and b.accounts is None


def test_bundle_holds_injected():
    sentinel = object()
    b = ServiceBundle(browser=sentinel)
    assert b.browser is sentinel
