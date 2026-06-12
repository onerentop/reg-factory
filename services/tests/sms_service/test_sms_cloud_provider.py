"""SmsCloudProvider 单元测试。用 httpx.MockTransport mock 真实 HTTP，
断言鉴权头(apiKey)、端点路径、信封解析(data.*)、错误(code!=0)抛异常。"""
import asyncio

import httpx
import pytest

from sms_service.providers.sms_cloud import SmsCloudProvider
from sms_service.providers.base import OrderStatus

API = "https://smscloud.sbs/api/system"


def patch_http(monkeypatch, handler):
    """把 httpx.AsyncClient 换成带 MockTransport(handler) 的版本。
    handler(request)->httpx.Response，可借 request 断言 headers/url/params。"""
    real_client = httpx.AsyncClient  # 先抓原始构造器，避免 fake 内部递归调到自己
    def fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


def provider():
    return SmsCloudProvider({"api_key": "K123", "base_url": API})


async def test_get_balance_parses_data_balance(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "操作成功", "data": {"balance": 8.0}})

    patch_http(monkeypatch, handler)
    bal = await provider().get_balance()
    assert bal == 8.0


async def test_get_balance_sends_apikey_header_and_correct_endpoint(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "", "data": {"balance": 1.0}})

    patch_http(monkeypatch, handler)
    await provider().get_balance()
    assert captured["req"].headers["apiKey"] == "K123"
    assert captured["req"].url.path.endswith("/public/sms/balance")


async def test_error_envelope_raises_valueerror(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={"code": 40001, "message": "登录凭证已过期", "data": None})

    patch_http(monkeypatch, handler)
    with pytest.raises(ValueError, match="40001"):
        await provider().get_balance()
