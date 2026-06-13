import httpx
import pytest
from sms_service.providers.sms_activate_base import SmsActivateProvider
from sms_service.providers.sms_cloud import SmsCloudProvider


def patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    def fake(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(httpx, "AsyncClient", fake)


class _P(SmsActivateProvider):
    name = "testp"
    _default_base_url = "https://x.test/handler_api.php"


async def test_sms_activate_get_prices(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, json={
        "52": {"go": {"cost": 0.1, "count": 12112}},
        "4": {"go": {"cost": 0.025, "count": 500}},
    }))
    rows = await _P({"api_key": "K"}).get_prices("go")
    # 按 cost 升序：4(0.025) 在 52(0.1) 前
    assert rows[0]["country"] == "4" and rows[0]["cost"] == 0.025 and rows[0]["count"] == 500
    assert rows[1]["country"] == "52" and rows[1]["cost"] == 0.1 and rows[1]["count"] == 12112


async def test_get_prices_empty_response(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="NO_ACTIVATION"))
    rows = await _P({"api_key": "K"}).get_prices("go")
    assert rows == []


async def test_sms_cloud_get_prices(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, json={"code": 0, "data": [
        {"country": 187, "countryName": "美国", "count": 287628, "retailPrice": 12.0},
        {"country": 4, "countryName": "菲律宾", "count": 100, "retailPrice": 0.3},
    ]}))
    rows = await SmsCloudProvider({"api_key": "K", "base_url": "https://smscloud.sbs/api/system"}).get_prices("go")
    assert rows[0]["country"] == "4" and rows[0]["cost"] == 0.3 and rows[0]["country_name"] == "菲律宾" and rows[0]["count"] == 100
    assert rows[1]["country"] == "187" and rows[1]["cost"] == 12.0 and rows[1]["count"] == 287628


async def test_sms_cloud_get_prices_non_list(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, json={"code": 0, "data": {}}))
    rows = await SmsCloudProvider({"api_key": "K", "base_url": "https://smscloud.sbs/api/system"}).get_prices("go")
    assert rows == []
