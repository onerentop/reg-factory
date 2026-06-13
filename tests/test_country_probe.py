from common.country_probe import build_probe_sequence, mark_available, mark_failed
import common.country_probe as cp


# ---- build_probe_sequence ----
def test_sequence_available_first_then_new_by_price():
    prices = [
        {"country": "4", "country_name": "菲律宾", "cost": 0.025, "count": 100},
        {"country": "52", "country_name": "泰国", "cost": 0.1, "count": 100},
        {"country": "8", "country_name": "肯尼亚", "cost": 0.02, "count": 100},
        {"country": "99", "country_name": "贵国", "cost": 0.5, "count": 100},  # 超 max_price
    ]
    probe = {"available": [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1000}], "failed": {}}
    seq = build_probe_sequence(prices, probe, max_price=0.2, now=2000)
    # available(泰国)优先 → 未试国家按价升序(肯尼亚0.02、菲律宾0.025)；超价的99跳过
    assert [s["country"] for s in seq] == ["52", "8", "4"]
    assert seq[0]["name"] == "泰国" and seq[1]["name"] == "肯尼亚"


def test_sequence_skips_failed_in_cooldown():
    prices = [{"country": "7", "country_name": "马来", "cost": 0.1, "count": 100}]
    probe = {"available": [], "failed": {"7": {"reason": "x", "last_fail": 2000}}}
    assert build_probe_sequence(prices, probe, max_price=0.2, now=3000, cooldown_seconds=86400) == []
    seq = build_probe_sequence(prices, probe, max_price=0.2, now=2000 + 90000, cooldown_seconds=86400)
    assert [s["country"] for s in seq] == ["7"]


# ---- mark_available / mark_failed ----
def test_mark_available_adds_and_clears_failed():
    probe = {"available": [], "failed": {"52": {"reason": "x", "last_fail": 1}}}
    mark_available(probe, "52", "泰国", 0.1, 2000)
    assert probe["available"] == [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 2000}]
    assert "52" not in probe["failed"]


def test_mark_available_replaces_existing():
    probe = {"available": [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1}], "failed": {}}
    mark_available(probe, "52", "泰国", 0.12, 3000)
    assert len(probe["available"]) == 1 and probe["available"][0]["last_ok"] == 3000


def test_mark_failed_demotes_available():
    probe = {"available": [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1}], "failed": {}}
    mark_failed(probe, "52", "用过太多次", 2000)
    assert probe["available"] == []
    assert probe["failed"]["52"] == {"reason": "用过太多次", "last_fail": 2000}


# ---- probe_load / probe_save / probe_prices (mock requests) ----
def test_probe_load_parses_value(monkeypatch):
    class _R:
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": {"value": {"available": [{"country": "52"}], "failed": {}}}}
    monkeypatch.setattr(cp.requests, "get", lambda *a, **k: _R())
    probe = cp.probe_load()
    assert probe["available"][0]["country"] == "52" and probe["failed"] == {}


def test_probe_load_defaults_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("conn")
    monkeypatch.setattr(cp.requests, "get", boom)
    assert cp.probe_load() == {"available": [], "failed": {}}


def test_probe_save_puts_key_and_value(monkeypatch):
    captured = {}
    def fake_put(url, json=None, **k):
        captured["url"] = url
        captured["json"] = json
        return object()
    monkeypatch.setattr(cp.requests, "put", fake_put)
    cp.probe_save({"available": [], "failed": {}})
    assert captured["url"].endswith("/config/gmail_country_probe")
    assert captured["json"]["key"] == "gmail_country_probe"
    assert captured["json"]["value"] == {"available": [], "failed": {}}


def test_probe_prices_returns_data(monkeypatch):
    class _R:
        def json(self):
            return {"data": [{"country": "52", "country_name": "泰国", "cost": 0.1, "count": 9}]}
    monkeypatch.setattr(cp.requests, "get", lambda *a, **k: _R())
    rows = cp.probe_prices("hero_sms")
    assert rows[0]["country"] == "52"


def test_sequence_available_in_cooldown_filtered():
    prices = [{"country": "52", "country_name": "泰国", "cost": 0.1, "count": 100}]
    probe = {"available": [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1}],
             "failed": {"52": {"reason": "x", "last_fail": 2000}}}
    # 52 在 available 但也在 failed 冷却内 → 过滤，候选为空
    seq = build_probe_sequence(prices, probe, max_price=0.2, now=3000, cooldown_seconds=86400)
    assert seq == []
