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


def test_create_browser_raises_when_no_profile_id():
    p, call = _provider_with_fake_call()
    call.return_value = {"ok": True}   # 无 profileId
    with pytest.raises(RuntimeError):
        p.create_browser(name="reg", proxy_str=None)


def test_call_retries_on_network_error_then_raises():
    p = AntBrowserProvider(base="http://127.0.0.1:19876", api_key="")
    p.retries = 2
    import urllib.error
    with patch("common.ant_provider.urllib.request.urlopen",
               side_effect=urllib.error.URLError("connection refused")) as u, \
         patch("common.ant_provider.time.sleep"):
        with pytest.raises(AntAPIError):
            p._call("GET", "/api/health")
    assert u.call_count == 3   # retries+1 = 3 次尝试


def test_call_raises_immediately_on_4xx():
    p = AntBrowserProvider(base="http://127.0.0.1:19876", api_key="")
    p.retries = 2
    import urllib.error, io
    err = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error":"bad"}'))
    with patch("common.ant_provider.urllib.request.urlopen", side_effect=err) as u, \
         patch("common.ant_provider.time.sleep"):
        with pytest.raises(AntAPIError):
            p._call("POST", "/api/profiles", {"x": 1})
    assert u.call_count == 1   # 4xx 不重试


def test_call_retries_on_5xx():
    p = AntBrowserProvider(base="http://127.0.0.1:19876", api_key="")
    p.retries = 2
    import urllib.error, io
    def make_err(*a, **k):
        raise urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b'busy'))
    with patch("common.ant_provider.urllib.request.urlopen", side_effect=make_err) as u, \
         patch("common.ant_provider.time.sleep"):
        with pytest.raises(AntAPIError):
            p._call("GET", "/api/health")
    assert u.call_count == 3   # 5xx 重试
