# -*- coding: utf-8 -*-
"""
common/sms.py — 参数化接码客户端(firefox.fun 主用 + hero-sms 兜底)。

提供 Google 网页注册使用的可参数化接码函数。

firefox.fun: act=getPhone/getPhoneCode/cancelPhone, iid=项目号
hero-sms(sms-activate 兼容): action=getNumber/getStatus/setStatus, service=服务码。
"""

import re
import time

import requests

from config import (
    SMS_API_BASE,
    SMS_TOKEN,
    HERO_SMS_API_BASE,
    HERO_SMS_API_KEY,
    SMS_HERO_COUNTRIES,
)

HERO_SMS_COUNTRY_PREFER = SMS_HERO_COUNTRIES


def get_phone(project_id, hero_service, country_prefer=("",), country_blacklist=(),
              max_retries=5, max_price="0", hero_country=None, hero_operator=None,
              hero_fixed_price=False):
    """返回 (phone, country_code, pkey)。firefox.fun 优先，没号转 hero-sms。
    hero-sms 的 phone 已含国家码、country_code 返回 ''。
    max_price: firefox.fun 价格上限，'0' 只取最便宜(常是垃圾号段)，给够才摸得到好国家。
    hero_country: 指定 hero-sms 国家 ID（如 '52'=泰国）；None=按价格自动选(最便宜常被 Google 拒)。"""
    if SMS_TOKEN and project_id:
        for country in country_prefer:
            attempts = max_retries if country == "" else 1
            for attempt in range(attempts):
                try:
                    resp = requests.get(SMS_API_BASE, params={
                        "act": "getPhone", "token": SMS_TOKEN, "iid": project_id,
                        "did": "", "country": country, "dock": "", "otpmode": "",
                        "maxPrice": str(max_price), "mobile": "", "pushUrl": "",
                    }, timeout=30)
                except Exception as e:
                    print(f"  [sms] err: {e}")
                    break
                text = resp.text.strip()
                print(f"  [sms] api(country={country or 'any'}, try={attempt+1}): {text}")
                parts = text.split("|")
                if parts[0] == "1" and len(parts) >= 8:
                    pkey, country_code, phone = parts[1], parts[4], parts[7]
                    if country_code in country_blacklist:
                        print(f"  [sms] +{country_code} blacklisted, releasing...")
                        release(pkey)
                        time.sleep(1)
                        continue
                    print(f"  [sms] phone: +{country_code}{phone} (pkey={pkey})")
                    return phone, country_code, pkey
                break

    print("  [sms] firefox.fun 无号/未配，转 hero-sms...")
    res = _hero_get_phone(hero_service, country_override=hero_country,
                          operator=hero_operator, max_price=max_price, fixed_price=hero_fixed_price)
    if res:
        full_phone, pkey = res
        return full_phone, "", pkey
    raise RuntimeError("get phone failed: 所有平台都没号")


def get_code(pkey, max_wait=180, interval=5):
    if str(pkey).startswith("hero_"):
        return _hero_get_code(pkey, max_wait, interval)
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(SMS_API_BASE, params={"act": "getPhoneCode", "token": SMS_TOKEN, "pkey": pkey}, timeout=30)
            parts = resp.text.strip().split("|")
            if parts[0] == "1" and len(parts) >= 2:
                code = parts[1]
                print(f"  [sms] code: {code}")
                return code
        except Exception:
            pass
        print(f"  waiting sms... ({int(time.time()-start)}s/{max_wait}s)")
        time.sleep(interval)
    return None


def release(pkey):
    if str(pkey).startswith("hero_"):
        _hero_release(pkey)
        return
    try:
        requests.get(SMS_API_BASE, params={"act": "cancelPhone", "token": SMS_TOKEN, "pkey": pkey}, timeout=10)
    except Exception:
        pass


# ---------------- hero-sms ----------------
def _hero_get_phone(service, country_override=None, operator=None, max_price=None, fixed_price=False):
    if not (HERO_SMS_API_KEY and service):
        return None
    # 指定国家(可指定运营商/价格档取更干净号池)：直接取，跳过价格排序
    if country_override is not None:
        params = {
            "api_key": HERO_SMS_API_KEY, "action": "getNumber",
            "service": service, "country": str(country_override),
        }
        if operator:
            params["operator"] = operator
        if max_price and str(max_price) not in ("0", "0.0", ""):
            params["maxPrice"] = str(max_price)
            # fixedPrice=true 配 maxPrice：严格按该价档买(不取最便宜)，命中指定号池
            if fixed_price:
                params["fixedPrice"] = "true"
        try:
            r = requests.get(HERO_SMS_API_BASE, params=params, timeout=30)
            text = r.text.strip()
            if text.startswith("ACCESS_NUMBER:"):
                _, act_id, full_phone = text.split(":")[:3]
                tag = f"country={country_override}" + (f"/{operator}" if operator else "")
                print(f"  [hero-sms] {tag}: +{full_phone} (id={act_id})")
                return full_phone, f"hero_{act_id}"
            print(f"  [hero-sms] country={country_override} op={operator}: {text}")
        except Exception as e:
            print(f"  [hero-sms] err country={country_override}: {e}")
        return None
    countries = HERO_SMS_COUNTRY_PREFER
    try:
        r = requests.get(HERO_SMS_API_BASE, params={"api_key": HERO_SMS_API_KEY, "action": "getPrices", "service": service}, timeout=15)
        prices = r.json()
        ranked = []
        for cid, svc in prices.items():
            info = svc.get(service, {})
            if info.get("count", 0) > 0 and info.get("cost", 999) < 1.0:
                ranked.append((info["cost"], -info["count"], int(cid)))
        ranked.sort()
        if ranked:
            countries = [c for _, _, c in ranked]
            print(f"  [hero-sms] {len(countries)} countries (cheapest ${ranked[0][0]} id={ranked[0][2]})")
    except Exception as e:
        print(f"  [hero-sms] getPrices failed: {e}")
    for country in countries:
        try:
            r = requests.get(HERO_SMS_API_BASE, params={
                "api_key": HERO_SMS_API_KEY, "action": "getNumber", "service": service, "country": country,
            }, timeout=30)
            text = r.text.strip()
            if text.startswith("ACCESS_NUMBER:"):
                _, act_id, full_phone = text.split(":")[:3]
                print(f"  [hero-sms] country={country}: +{full_phone} (id={act_id})")
                return full_phone, f"hero_{act_id}"
        except Exception as e:
            print(f"  [hero-sms] err country={country}: {e}")
    return None


def _hero_get_code(pkey, max_wait=180, interval=5):
    act_id = str(pkey).replace("hero_", "")
    try:
        requests.get(HERO_SMS_API_BASE, params={"api_key": HERO_SMS_API_KEY, "action": "setStatus", "id": act_id, "status": 1}, timeout=10)
    except Exception:
        pass
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = requests.get(HERO_SMS_API_BASE, params={"api_key": HERO_SMS_API_KEY, "action": "getStatus", "id": act_id}, timeout=30)
            text = r.text.strip()
            if text.startswith("STATUS_OK:"):
                code = text.split(":")[1]
                m = re.search(r"\d{4,8}", code)
                print(f"  [hero-sms] code: {code}")
                return m.group(0) if m else code
            if text == "STATUS_CANCEL":
                return None
        except Exception:
            pass
        print(f"  [hero-sms] waiting... ({int(time.time()-start)}s/{max_wait}s)")
        time.sleep(interval)
    return None


def _hero_release(pkey):
    act_id = str(pkey).replace("hero_", "")
    try:
        requests.get(HERO_SMS_API_BASE, params={"api_key": HERO_SMS_API_KEY, "action": "setStatus", "id": act_id, "status": 8}, timeout=10)
    except Exception:
        pass
