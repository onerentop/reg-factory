from unittest.mock import MagicMock, patch

import pytest

from common.ant_provider import AntBrowserProvider, AntAPIError
from common.browser_provider import BrowserProvider


def _provider_with_fake_call():
    p = AntBrowserProvider(base="http://127.0.0.1:19876", api_key="")
    p._call = MagicMock()      # 注入 fake，绕过真实 HTTP
    return p, p._call


def test_is_browser_provider():
    assert isinstance(AntBrowserProvider(), BrowserProvider)


def test_create_browser_direct_when_no_proxy():
    p, call = _provider_with_fake_call()
    call.return_value = {"profileId": "uuid-1", "ok": True}
    pid = p.create_browser(name="reg_1", proxy_str=None)
    assert pid == "uuid-1"
    method, path, body = call.call_args[0]
    assert method == "POST" and path == "/api/profiles"
    assert body["profile"]["profileName"] == "reg_1"
    assert body["profile"]["proxyConfig"] == "direct://"


def test_create_browser_passes_proxy_str_as_proxyconfig():
    p, call = _provider_with_fake_call()
    call.return_value = {"profileId": "uuid-2"}
    p.create_browser(name="reg", proxy_str="http://u:p@1.2.3.4:8080")
    body = call.call_args[0][2]
    assert body["profile"]["proxyConfig"] == "http://u:p@1.2.3.4:8080"


def test_create_browser_empty_proxy_is_direct():
    p, call = _provider_with_fake_call()
    call.return_value = {"profileId": "uuid-3"}
    p.create_browser(name="reg", proxy_str="   ")
    assert call.call_args[0][2]["profile"]["proxyConfig"] == "direct://"
