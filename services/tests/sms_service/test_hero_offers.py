"""HeroSmsProvider.get_offers 单测：mock HeroSMS v1 /activations/offers，
断言价位阶梯(tiers)排序 + 价格/库存解析 + v1 鉴权头与端点。"""
import httpx

from sms_service.providers.hero_sms import HeroSmsProvider


def patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    def fake(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(httpx, "AsyncClient", fake)


def _provider():
    return HeroSmsProvider({"api_key": "K123", "base_url": "https://hero-sms.com/stubs/handler_api.php"})


async def test_hero_get_offers_parses_tiers(monkeypatch):
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["auth"] = req.headers.get("Authorization")
        return httpx.Response(200, json={"data": {"go": {"52": {
            "prices": {"default": 0.1, "retail": 0.12, "min": 0.0589},
            "counts": {"total": 2487, "physical": 1343, "defaultPrice": 1500},
            "map": {"0.1000": 100, "0.1510": 500, "0.0589": 50},
        }}}})

    patch_http(monkeypatch, handler)
    offers = await _provider().get_offers("go", "52")

    # v1 端点 + header 鉴权
    assert "/api/v1/activations/offers" in captured["url"]
    assert captured["auth"] == "ApiKey K123"
    # 价格/库存
    assert offers["counts"]["total"] == 2487
    assert offers["prices"]["min"] == 0.0589
    # 价位阶梯按 price 升序
    prices = [t["price"] for t in offers["tiers"]]
    assert prices == [0.0589, 0.1, 0.151]
    assert offers["tiers"][0]["count"] == 50


async def test_hero_get_offers_empty_when_country_missing(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, json={"data": {"go": {}}}))
    offers = await _provider().get_offers("go", "52")
    assert offers["tiers"] == [] and offers["prices"] == {} and offers["counts"] == {}
