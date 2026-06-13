"""SmsBowerProvider.get_offers 单测：mock getPricesV2 价位阶梯 {价格:数量}。"""
import httpx

from sms_service.providers.sms_bower import SmsBowerProvider


def patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    def fake(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(httpx, "AsyncClient", fake)


def _provider():
    return SmsBowerProvider({"api_key": "K123", "base_url": "https://smsbower.page/stubs/handler_api.php"})


async def test_sms_bower_get_offers_parses_v2_tiers(monkeypatch):
    captured = {}

    def handler(req):
        captured["params"] = dict(req.url.params)
        # getPricesV2: {国家:{服务:{价格:数量}}}，价格乱序
        return httpx.Response(200, text='{"7":{"go":{"0.15":500,"0.1":50,"0.2":800}}}')

    patch_http(monkeypatch, handler)
    offers = await _provider().get_offers("go", "7")

    assert captured["params"]["action"] == "getPricesV2"
    assert captured["params"]["service"] == "go" and captured["params"]["country"] == "7"
    # 价位阶梯按 price 升序
    assert [t["price"] for t in offers["tiers"]] == [0.1, 0.15, 0.2]
    assert offers["tiers"][0]["count"] == 50
    # 库存合计 + 最低价
    assert offers["counts"]["total"] == 1350
    assert offers["prices"]["min"] == 0.1


async def test_sms_bower_get_offers_empty_on_no_numbers(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="NO_NUMBERS"))
    offers = await _provider().get_offers("go", "7")
    assert offers["tiers"] == [] and offers["prices"]["min"] == 0 and offers["counts"]["total"] == 0
