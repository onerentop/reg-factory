"""Gmail 注册国家可用性探测：候选序列策略 + 可用库读写。
纯函数易测；HTTP helper 经 gateway 读写 config_service。"""

import requests

_GW = "http://localhost:8000"
_NOPROXY = {"http": None, "https": None}


def build_probe_sequence(prices, probe, max_price, now, cooldown_seconds=86400):
    """构建候选国家序列：available(可用库,按价升序)优先 + 未试国家(按价升序)，
    全部 cost ≤ max_price 且跳过 failed 冷却内的国家。
    prices: [{country, country_name, cost, count}]；probe: {available:[...], failed:{...}}
    返回 [{country, name, price}]。"""
    mp = float(max_price)
    failed = probe.get("failed", {}) or {}

    def in_cooldown(c):
        f = failed.get(str(c))
        return bool(f) and (now - f.get("last_fail", 0) < cooldown_seconds)

    avail_seq, avail_ids = [], set()
    for a in probe.get("available", []) or []:
        c = str(a["country"])
        avail_ids.add(c)
        if float(a.get("price", 0)) <= mp and not in_cooldown(c):
            avail_seq.append({"country": c, "name": a.get("name", ""), "price": float(a.get("price", 0))})
    avail_seq.sort(key=lambda x: x["price"])

    new_seq = []
    for p in prices:
        c = str(p["country"])
        if c in avail_ids or in_cooldown(c) or float(p.get("cost", 0)) > mp:
            continue
        new_seq.append({"country": c, "name": p.get("country_name", ""), "price": float(p.get("cost", 0))})
    new_seq.sort(key=lambda x: x["price"])
    return avail_seq + new_seq


def mark_available(probe, country, name, price, now):
    """记/更新可用国家；从 failed 移除。原地改 probe。"""
    c = str(country)
    probe.setdefault("available", [])
    probe.setdefault("failed", {})
    probe["available"] = [a for a in probe["available"] if str(a["country"]) != c]
    probe["available"].append({"country": c, "name": name, "price": float(price), "last_ok": now})
    probe["failed"].pop(c, None)


def mark_failed(probe, country, reason, now):
    """记失败国家(进冷却)；若在 available 则移除(降级)。原地改 probe。"""
    c = str(country)
    probe.setdefault("available", [])
    probe.setdefault("failed", {})
    probe["available"] = [a for a in probe["available"] if str(a["country"]) != c]
    probe["failed"][c] = {"reason": reason, "last_fail": now}


def probe_load(base_url=_GW):
    """GET 可用库；异常/缺失 → 空库。"""
    try:
        r = requests.get(f"{base_url}/config/gmail_country_probe", timeout=10, proxies=_NOPROXY)
        r.raise_for_status()
        v = (r.json().get("data") or {}).get("value")
        if isinstance(v, dict):
            v.setdefault("available", [])
            v.setdefault("failed", {})
            return v
    except Exception as e:
        print(f"[probe] load err: {e}")
    return {"available": [], "failed": {}}


def probe_save(probe, base_url=_GW):
    """PUT 回写可用库（body 必须含 key）。"""
    try:
        requests.put(f"{base_url}/config/gmail_country_probe",
                     json={"key": "gmail_country_probe", "value": probe},
                     timeout=10, proxies=_NOPROXY)
    except Exception as e:
        print(f"[probe] save err: {e}")


def probe_prices(provider, base_url=_GW):
    """GET 该 provider 的全量国家+价格（go 服务）。"""
    try:
        r = requests.get(f"{base_url}/sms/providers/{provider}/prices",
                         params={"service": "go"}, timeout=20, proxies=_NOPROXY)
        d = r.json().get("data")
        return d if isinstance(d, list) else []
    except Exception:
        return []
