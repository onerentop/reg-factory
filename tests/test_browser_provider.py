import pytest
from common.browser_provider import BrowserProvider


def test_browser_provider_is_abstract():
    # 抽象基类不能直接实例化
    with pytest.raises(TypeError):
        BrowserProvider()


def test_factory_returns_browser_provider():
    from common.browser_provider import get_browser_provider
    p = get_browser_provider()
    assert isinstance(p, BrowserProvider)
