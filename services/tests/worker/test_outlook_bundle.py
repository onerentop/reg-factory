from worker.capabilities.outlook_bundle import default_outlook_bundle
from worker.capabilities.browser import IxBrowserService
from worker.capabilities.token import GraphTokenExtractor
from worker.capabilities.bundle import ServiceBundle


def test_default_bundle_assembles_browser_and_tokens():
    b = default_outlook_bundle()
    assert isinstance(b, ServiceBundle)
    assert isinstance(b.browser, IxBrowserService)
    assert isinstance(b.tokens, GraphTokenExtractor)


def test_default_bundle_defers_captcha_and_proxy():
    # M2a：captcha/proxy 等依赖根抽取，尚未注入
    b = default_outlook_bundle()
    assert b.captcha is None
    assert b.proxy is None
