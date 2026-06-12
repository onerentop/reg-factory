import asyncio
import pytest
from worker.capabilities.interfaces import (
    BrowserSession, EmailAccount,
    BrowserService, ProxyService, CaptchaService, CaptchaResolver,
    EmailPoolService, SmsService, TokenExtractor,
)


@pytest.mark.parametrize("abc_cls", [
    BrowserService, ProxyService, CaptchaService,
    EmailPoolService, SmsService, TokenExtractor,
])
def test_abstract_cannot_instantiate(abc_cls):
    with pytest.raises(TypeError):
        abc_cls()


def test_value_objects_hold_fields():
    s = BrowserSession(page="p", context="c", profile_id="id", proxy="px")
    assert s.page == "p" and s.profile_id == "id"
    a = EmailAccount(email="e@x.com", password="pw")
    assert a.email == "e@x.com" and a.password == "pw" and a.refresh_token is None


def test_captcha_resolver_dispatches_by_kind():
    class _PX(CaptchaService):
        kind = "perimeterx"
        async def solve(self, page, context): return True

    resolver = CaptchaResolver()
    resolver.register(_PX())
    assert asyncio.run(resolver.solve("perimeterx", page=None, context={})) is True


def test_captcha_resolver_unknown_kind_raises():
    resolver = CaptchaResolver()
    with pytest.raises(KeyError):
        asyncio.run(resolver.solve("nope", page=None, context={}))
