import httpx
from sms_service.providers.sms_activate_base import SmsActivateProvider


def patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    def fake(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(httpx, "AsyncClient", fake)


class _P(SmsActivateProvider):
    name = "testp"
    _default_base_url = "https://x.test/handler_api.php"


async def test_get_number_passes_price(monkeypatch):
    captured = {}
    def handler(req):
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, text="ACCESS_NUMBER:12345:66812345678")
    patch_http(monkeypatch, handler)
    await _P({"api_key": "K"}).get_number("go", "52", max_price="0.2", fixed_price=False)
    assert captured["params"].get("maxPrice") == "0.2"
    assert "fixedPrice" not in captured["params"]  # fixed_price=False 不带


async def test_get_number_fixed_price_sends_flag(monkeypatch):
    captured = {}
    def handler(req):
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, text="ACCESS_NUMBER:1:2")
    patch_http(monkeypatch, handler)
    await _P({"api_key": "K"}).get_number("go", "52", max_price="0.2", fixed_price=True)
    assert captured["params"].get("maxPrice") == "0.2"
    assert captured["params"].get("fixedPrice") == "true"
