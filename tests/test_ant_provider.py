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


def test_open_browser_returns_http_endpoint_from_debugport():
    p, call = _provider_with_fake_call()
    call.return_value = {"debugPort": 46602, "debugReady": True, "ok": True}
    data = p.open_browser("uuid-1")
    assert data == {"ws": "http://127.0.0.1:46602", "http": "http://127.0.0.1:46602"}
    method, path, body = call.call_args[0]
    assert method == "POST" and path == "/api/launch"
    assert body == {"profileId": "uuid-1"}


def test_open_browser_polls_when_launch_not_ready():
    p, call = _provider_with_fake_call()
    # 第一次 launch 未就绪,随后 runtime/active 就绪
    call.side_effect = [
        {"debugReady": False, "debugPort": 0},                        # launch
        {"profileId": "uuid-1", "debugReady": True, "debugPort": 55000},  # runtime/active
    ]
    data = p.open_browser("uuid-1")
    assert data["http"] == "http://127.0.0.1:55000"


def test_open_browser_raises_when_never_ready():
    p, call = _provider_with_fake_call()
    call.return_value = {"debugReady": False, "debugPort": 0}
    with patch("common.ant_provider.time.sleep"):      # 免真 sleep 15s
        with pytest.raises(AntAPIError):
            p.open_browser("uuid-1")


def test_close_browser_stops_with_profile_selector():
    p, call = _provider_with_fake_call()
    call.return_value = {"ok": True}
    p.close_browser("uuid-1")
    method, path, body = call.call_args[0]
    assert method == "POST" and path == "/api/runtime/stop"
    assert body == {"profileId": "uuid-1"}


def test_close_browser_swallows_errors():
    p, call = _provider_with_fake_call()
    call.side_effect = AntAPIError(400, "POST", "/api/runtime/stop", "bad")
    p.close_browser("uuid-1")   # 不抛


def test_delete_browser_stops_then_deletes():
    p, call = _provider_with_fake_call()
    call.return_value = {"ok": True}
    p.delete_browser("uuid-1")
    paths = [c[0][1] for c in call.call_args_list]
    assert "/api/runtime/stop" in paths
    assert "/api/profiles/uuid-1" in paths


def test_delete_browser_swallows_errors():
    p, call = _provider_with_fake_call()
    call.side_effect = AntAPIError(409, "DELETE", "/api/profiles/uuid-1", "running")
    p.delete_browser("uuid-1")   # 不抛


def test_list_browsers_maps_fields():
    p, call = _provider_with_fake_call()
    call.return_value = {"count": 2, "items": [
        {"profileId": "a", "profileName": "n1", "userDataDir": "d1"},
        {"profileId": "b", "profileName": "n2", "userDataDir": "d2"},
    ]}
    out = p.list_browsers()
    rows = out["data"]["list"]
    assert rows[0] == {"id": "a", "name": "n1", "remark": "d1", "seq": "a"}
    assert len(rows) == 2


def test_cleanup_browsers_deletes_beyond_keep():
    p, call = _provider_with_fake_call()
    # 第一次 _call 是 GET /api/profiles(列表),之后是 stop/delete(吞异常)
    call.side_effect = [
        {"items": [{"profileId": "a"}, {"profileId": "b"}, {"profileId": "c"}]},
    ] + [{"ok": True}] * 10
    n = p.cleanup_browsers(keep=1)
    assert n == 2   # 保留 1 个,删 2 个


def test_factory_returns_ant_when_configured(monkeypatch):
    import common.browser_provider as bp
    monkeypatch.setattr("config.BROWSER_PROVIDER", "ant", raising=False)
    bp._PROVIDER = None            # 重置单例
    p = bp.get_browser_provider()
    assert isinstance(p, AntBrowserProvider)
    bp._PROVIDER = None            # 清理,免污染其它测试
