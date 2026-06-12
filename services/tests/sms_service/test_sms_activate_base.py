"""SmsActivateProvider 基类单测。MockTransport mock handler_api 纯文本响应。
用测试桩 _P 隔离基类逻辑，不依赖具体平台。"""
import asyncio

import httpx
import pytest

from sms_service.providers.sms_activate_base import SmsActivateProvider
from sms_service.providers.base import OrderStatus


def patch_http(monkeypatch, handler):
    """把 httpx.AsyncClient 换成带 MockTransport(handler) 的版本。
    先抓原始构造器，避免 fake 内部递归调到自己。"""
    real_client = httpx.AsyncClient
    def fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


class _P(SmsActivateProvider):
    name = "testp"
    _default_base_url = "https://x.test/handler_api.php"


def provider():
    return _P({"api_key": "K123"})


async def test_get_balance_parses(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="ACCESS_BALANCE:1.1947"))
    assert await provider().get_balance() == 1.1947


async def test_get_balance_error_raises(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="BAD_KEY"))
    with pytest.raises(ValueError, match="BAD_KEY"):
        await provider().get_balance()


async def test_request_sends_apikey_and_action(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_BALANCE:1")

    patch_http(monkeypatch, handler)
    await provider().get_balance()
    q = dict(captured["req"].url.params)
    assert q["api_key"] == "K123"
    assert q["action"] == "getBalance"


async def test_get_number_parses(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_NUMBER:12345:79001234567")

    patch_http(monkeypatch, handler)
    res = await provider().get_number("tg", "0")
    assert res.order_id == "12345"
    assert res.phone_number == "79001234567"
    assert res.provider == "testp"
    q = dict(captured["req"].url.params)
    assert q["action"] == "getNumber"
    assert q["service"] == "tg"
    assert q["country"] == "0"


async def test_get_number_error_raises(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="NO_NUMBERS"))
    with pytest.raises(ValueError, match="NO_NUMBERS"):
        await provider().get_number("tg", "0")


async def test_get_code_received(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="STATUS_OK:654321")

    patch_http(monkeypatch, handler)
    res = await provider().get_code("999", timeout=10)
    assert res.code == "654321"
    assert res.status == OrderStatus.RECEIVED
    q = dict(captured["req"].url.params)
    assert q["action"] == "getStatus"
    assert q["id"] == "999"


async def test_get_code_cancelled(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="STATUS_CANCEL"))
    res = await provider().get_code("999", timeout=10)
    assert res.code is None
    assert res.status == OrderStatus.CANCELLED


async def test_get_code_timeout(monkeypatch):
    async def fast_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="STATUS_WAIT_CODE"))
    res = await provider().get_code("999", timeout=10)
    assert res.code is None
    assert res.status == OrderStatus.TIMEOUT


async def test_complete_sets_status_6(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_ACTIVATION")

    patch_http(monkeypatch, handler)
    await provider().complete("999")
    q = dict(captured["req"].url.params)
    assert q["action"] == "setStatus"
    assert q["id"] == "999"
    assert q["status"] == "6"


async def test_cancel_sets_status_8(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_CANCEL")

    patch_http(monkeypatch, handler)
    await provider().cancel("999")
    q = dict(captured["req"].url.params)
    assert q["action"] == "setStatus"
    assert q["id"] == "999"
    assert q["status"] == "8"
