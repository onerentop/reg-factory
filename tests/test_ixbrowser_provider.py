from unittest.mock import MagicMock

import pytest

from common.ixbrowser_provider import IXBrowserProvider
from common.browser_provider import BrowserProvider


def _provider_with_fake_client():
    p = IXBrowserProvider()
    fake = MagicMock()
    p._client = fake          # 注入 fake，绕过真实 IXBrowserClient
    return p, fake


def test_is_browser_provider():
    assert isinstance(IXBrowserProvider(), BrowserProvider)


def test_parse_proxy_userpass_default_http():
    assert IXBrowserProvider._parse_proxy("u:p@1.2.3.4:8080") == {
        "type": "http", "username": "u", "password": "p",
        "host": "1.2.3.4", "port": "8080",
    }


def test_parse_proxy_socks5_prefix():
    r = IXBrowserProvider._parse_proxy("socks5://u:p@1.2.3.4:1080")
    assert r["type"] == "socks5" and r["host"] == "1.2.3.4" and r["port"] == "1080"


def test_parse_proxy_host_port_only():
    assert IXBrowserProvider._parse_proxy("1.2.3.4:8080") == {
        "type": "http", "host": "1.2.3.4", "port": "8080",
    }


def test_parse_proxy_invalid_returns_none():
    assert IXBrowserProvider._parse_proxy("garbage") is None


def test_create_browser_default_kernel_unforced_and_returns_id():
    # 默认不强制内核版本（交给 ixBrowser 客户端默认内核，自动适配本机）
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = {"profile_id": 123}
    pid = p.create_browser(name="t")
    assert pid == 123
    profile = fake.create_profile.call_args[0][0]
    assert profile.fingerprint_config.kernel_version is None


def test_create_browser_with_proxy_builds_direct_and_stores_injection():
    # 新行为：有代理也把 profile 建成「直连」，绕过 ixBrowser open 时的服务端代理检测；
    # 代理暂存 _injected_proxy，留到 open_browser 用 --proxy-server 注入。
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = {"profile_id": 9}
    pid = p.create_browser(name="t", proxy_str="u:p@1.2.3.4:8080")
    profile = fake.create_profile.call_args[0][0]
    assert profile.proxy_config.proxy_ip is None          # 直连，代理未写进 profile
    assert p._injected_proxy[str(pid)]["host"] == "1.2.3.4"
    assert p._injected_proxy[str(pid)]["port"] == "8080"


def test_open_browser_injects_proxy_server_and_returns_auth():
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = {"profile_id": 9}
    p.create_browser(name="t", proxy_str="u:p@1.2.3.4:8080")
    fake.open_profile.return_value = {
        "ws": "ws://127.0.0.1:5/devtools/browser/x", "debugging_address": "127.0.0.1:5",
    }
    data = p.open_browser(9)
    kwargs = fake.open_profile.call_args.kwargs
    assert kwargs["startup_args"] == ["--proxy-server=http://1.2.3.4:8080"]
    assert data["proxy_auth"] == {"username": "u", "password": "p"}


def test_open_browser_without_injection_has_no_proxy_auth():
    p, fake = _provider_with_fake_client()
    fake.open_profile.return_value = {"ws": "ws://x", "debugging_address": "127.0.0.1:5"}
    data = p.open_browser(999)          # 无绑定代理
    assert fake.open_profile.call_args.kwargs["startup_args"] is None
    assert "proxy_auth" not in data


def test_delete_browser_clears_injection():
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = {"profile_id": 9}
    p.create_browser(name="t", proxy_str="u:p@1.2.3.4:8080")
    assert "9" in p._injected_proxy
    p.delete_browser(9)
    assert "9" not in p._injected_proxy


def test_open_browser_maps_ws_and_http():
    p, fake = _provider_with_fake_client()
    fake.open_profile.return_value = {
        "ws": "ws://127.0.0.1:5/devtools/browser/abc",
        "debugging_address": "127.0.0.1:5",
    }
    data = p.open_browser(7)
    assert data == {"ws": "ws://127.0.0.1:5/devtools/browser/abc", "http": "127.0.0.1:5"}


def test_open_browser_falls_back_to_http_endpoint_when_no_ws():
    p, fake = _provider_with_fake_client()
    fake.open_profile.return_value = {"ws": "", "debugging_address": "127.0.0.1:6"}
    data = p.open_browser(7)
    # ws 缺失时用 http endpoint 兜底，供 connect_over_cdp 自动发现
    assert data["ws"] == "http://127.0.0.1:6"


def test_call_raises_on_none_with_client_message():
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = None
    fake.message = "boom"
    fake.code = -1
    with pytest.raises(Exception):
        p.create_browser(name="t")


def test_list_browsers_converts_fields():
    p, fake = _provider_with_fake_client()
    fake.get_profile_list.return_value = [
        {"profile_id": 2, "name": "a", "note": "n2"},
        {"profile_id": 1, "name": "b", "note": "n1"},
    ]
    out = p.list_browsers()
    rows = out["data"]["list"]
    assert {"id", "name", "remark", "seq"} <= set(rows[0].keys())
    assert rows[0]["id"] == 2 and rows[0]["seq"] == 2


def test_parse_proxy_four_field_defaults_to_socks5_for_compat():
    """不传 default_type 时保持既有行为，1024proxy 调用方不受影响。"""
    assert IXBrowserProvider._parse_proxy("1.2.3.4:1080:u:p")["type"] == "socks5"


def test_parse_proxy_four_field_honours_explicit_type():
    assert IXBrowserProvider._parse_proxy("1.2.3.4:8080:u:p", default_type="http")["type"] == "http"


def test_parse_proxy_scheme_prefix_still_wins_over_default_type():
    """显式前缀优先于 default_type。"""
    assert IXBrowserProvider._parse_proxy(
        "socks5://u:p@1.2.3.4:1080", default_type="http")["type"] == "socks5"


def test_parse_proxy_userpass_form_honours_explicit_type():
    r = IXBrowserProvider._parse_proxy("u:p@1.2.3.4:8080", default_type="http")
    assert r["type"] == "http" and r["host"] == "1.2.3.4" and r["port"] == "8080"


def test_parse_proxy_host_port_form_honours_explicit_type():
    assert IXBrowserProvider._parse_proxy("1.2.3.4:8080", default_type="http")["type"] == "http"


def test_parse_proxy_still_returns_none_for_garbage_with_explicit_type():
    assert IXBrowserProvider._parse_proxy("garbage", default_type="http") is None
