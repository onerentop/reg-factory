"""Google/Gmail account registration via pure HTTP protocol.

Reverse-engineered from Android GMS batchexecute API.
Flow: name → birthday → username → password → phone verification → confirm → terms

Usage:
  python register_gmail_protocol.py
  python register_gmail_protocol.py --first Max --last Weber
  python register_gmail_protocol.py --proxy socks5://user:pass@host:port
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import string
import sys
import time
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import config  # noqa: F401  (loads .env)
except ImportError:
    pass

try:
    from common import sms as sms_client
except Exception:
    sms_client = None

# 数字国家码 → Google 期望的 ISO 国家码（小写，对齐抓包真实请求 "th"）
PHONE_CC_TO_ISO = {
    "1": "us", "7": "ru", "20": "eg", "31": "nl", "33": "fr", "34": "es",
    "36": "hu", "39": "it", "44": "gb", "48": "pl", "49": "de", "52": "mx",
    "55": "br", "56": "cl", "57": "co", "60": "my", "62": "id", "63": "ph",
    "66": "th", "77": "kz", "84": "vn", "86": "cn", "91": "in", "92": "pk",
    "212": "ma", "234": "ng", "261": "mg", "351": "pt", "380": "ua", "972": "il",
}


try:
    import phonenumbers as _pn
except Exception:
    _pn = None


def _split_intl_phone(full_phone):
    """把 '66812345678' 这种含国家码的全号拆成 (e164='+66812345678', iso='th')。
    优先用 phonenumbers 解析（支持全部国家），回退到内置映射表。"""
    digits = re.sub(r"\D", "", full_phone or "")
    e164 = "+" + digits
    if _pn is not None:
        try:
            num = _pn.parse(e164, None)
            region = _pn.region_code_for_number(num)
            if region:
                return e164, region.lower()
        except Exception:
            pass
    for length in (3, 2, 1):
        cc = digits[:length]
        if cc in PHONE_CC_TO_ISO:
            return e164, PHONE_CC_TO_ISO[cc]
    return e164, "us"

# ======================== Config ========================

CAPSOLVER_API_KEY = os.environ.get("CAPSOLVER_API_KEY", "")
RECAPTCHA_SITE_KEY = "6Lf-_ekqAAAAAO4AXrJISaHw4_bW76NcfwhLN7Is"
RECAPTCHA_PAGE_URL = "https://accounts.google.com/"

FIRST_NAMES = ["Max", "Felix", "Leon", "Paul", "Emma", "Sophie", "Anna", "Marie", "Laura", "Liam"]
LAST_NAMES = ["Mueller", "Schmidt", "Weber", "Fischer", "Wagner", "Becker", "Koch", "Braun"]

# Android device headers (Samsung S22 Ultra, Android 9, Chrome 129 WebView)
ANDROID_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 9; SM-S908E Build/TP1A.220624.014; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.70 "
        "Mobile Safari/537.36"
    ),
    "sec-ch-ua": '"Android WebView";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Android"',
    "sec-ch-ua-model": '"SM-S908E"',
    "sec-ch-ua-platform-version": '"9.0.0"',
    "sec-ch-ua-full-version": '"129.0.6668.70"',
    "sec-ch-ua-full-version-list": '"Android WebView";v="129.0.6668.70", "Not=A?Brand";v="8.0.0.0", "Chromium";v="129.0.6668.70"',
    "sec-ch-ua-arch": '""',
    "sec-ch-ua-bitness": '""',
    "sec-ch-ua-wow64": "?0",
    "sec-ch-ua-form-factors": '"Desktop"',
    "X-Same-Domain": "1",
    "X-Requested-With": "com.google.android.gms",
    # 真机抓包必带：标识 Android setup flow（对齐 gmail_recapture.flow）
    "x-goog-ext-278367001-jspb": '["GlifSetupAndroid"]',
    "Origin": "https://accounts.google.com",
    "Referer": "https://accounts.google.com/",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Priority": "u=1, i",
}

IMSI = "460009188843340"  # fake China Mobile IMSI

# ======================== Helpers ========================

def log(msg, level="INFO"):
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def rand_str(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def solve_recaptcha_enterprise(page_url=RECAPTCHA_PAGE_URL, site_key=RECAPTCHA_SITE_KEY, max_wait=120):
    """Use CapSolver to solve reCAPTCHA Enterprise (invisible)."""
    if not CAPSOLVER_API_KEY:
        log("  [capsolver] no API key", "WARN")
        return None
    try:
        payload = {
            "clientKey": CAPSOLVER_API_KEY,
            "task": {
                "type": "ReCaptchaV2EnterpriseTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": site_key,
                "isInvisible": True,
            },
        }
        resp = requests.post("https://api.capsolver.com/createTask", json=payload, timeout=30)
        data = resp.json()
        if data.get("errorId", 1) != 0:
            log(f"  [capsolver] create error: {data.get('errorDescription', data)}", "WARN")
            return None
        task_id = data["taskId"]
        log(f"  [capsolver] task: {task_id}")
        end = time.time() + max_wait
        while time.time() < end:
            time.sleep(5)
            resp = requests.post("https://api.capsolver.com/getTaskResult", json={
                "clientKey": CAPSOLVER_API_KEY, "taskId": task_id,
            }, timeout=30)
            result = resp.json()
            if result.get("status") == "ready":
                token = result.get("solution", {}).get("gRecaptchaResponse", "")
                log(f"  [capsolver] solved! token={token[:60]}...")
                return token
            if result.get("status") == "failed":
                log(f"  [capsolver] failed: {result.get('errorDescription', '')}", "WARN")
                return None
        log("  [capsolver] timeout", "WARN")
        return None
    except Exception as e:
        log(f"  [capsolver] error: {e}", "WARN")
        return None


def extract_token(html, patterns):
    """Extract a token from HTML using multiple regex patterns."""
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def batchexecute(session, rpcid, payload_json, source_path, fsid, bl, at_token,
                 reqid_counter, tl="", dsh="", extra_qs=None, rpc_type="generic"):
    """Execute a Google batchexecute RPC call.

    payload_json: the inner payload as a JSON string (will be embedded as string in f.req)
    """
    url = "https://accounts.google.com/lifecycle/_/AccountLifecyclePlatformSignupUi/data/batchexecute"

    qs = {
        "rpcids": rpcid,
        "source-path": source_path,
        "f.sid": fsid,
        "bl": bl,
        "hl": "zh-Hans-CN",
        "_reqid": str(reqid_counter),
        "rt": "c",
    }
    if tl:
        qs["TL"] = tl
    if dsh:
        qs["dsh"] = dsh
    if extra_qs:
        qs.update(extra_qs)

    # f.req 格式: [[["rpcid", "payload_as_string", null, "generic"]]]
    # payload_json 已经是 JSON 字符串，直接嵌入
    freq = json.dumps([[[rpcid, payload_json, None, rpc_type]]])

    body = urllib.parse.urlencode({
        "f.req": freq,
        "at": at_token,
    })

    # 真机抓包必带：x-goog-ext-391502476-jspb = ["<dsh>"]（每请求带 dsh）
    req_headers = {}
    if dsh:
        req_headers["x-goog-ext-391502476-jspb"] = json.dumps([dsh])

    resp = session.post(url, params=qs, data=body, headers=req_headers or None, timeout=30)

    # Parse batchexecute response (format: )]}\n\nNNN\n[JSON]\nNNN\n[JSON])
    text = resp.text
    result = None
    try:
        # Skip )]}' prefix
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("["):
                parsed = json.loads(line)
                if parsed and isinstance(parsed[0], list) and parsed[0][0] == "wrb.fr":
                    result = parsed[0][2]  # the response data string
                    break
    except Exception:
        pass

    return resp, result


# ======================== Registration Flow ========================

def register_gmail(
    first_name=None, last_name=None, password=None,
    birth_year=None, birth_month=None, birth_day=None,
    proxy_str=None, phone_number=None, sms_code=None,
    auto_sms=False, botguard=None,
):
    # botguard: dict，浏览器方案铸的 BotGuard 产物，键 eOY7Bb_token/eOY7Bb_meta/ZNd7Td_token/ZNd7Td_meta
    """Register a Gmail account via protocol."""

    first = first_name or random.choice(FIRST_NAMES)
    last = last_name or random.choice(LAST_NAMES)
    pw = password or f"Gm{rand_str(6)}!{random.randint(10, 99)}"
    year = birth_year or random.randint(1985, 1998)
    month = birth_month or random.randint(1, 12)
    day = birth_day or random.randint(1, 28)

    log(f"name: {first} {last}, born: {year}-{month:02d}-{day:02d}")
    log(f"password: {pw}")

    # Setup session
    session = requests.Session()
    if proxy_str:
        if proxy_str.startswith("socks"):
            session.proxies = {"http": proxy_str, "https": proxy_str}
        else:
            session.proxies = {"http": proxy_str, "https": proxy_str}
        log(f"proxy: {proxy_str[:50]}...")
    session.headers.update(ANDROID_HEADERS)

    reqid = random.randint(100000, 999999)

    # ---- Step 0: Initial entry (Android embedded setup) ----
    log("[0] loading signup entry...")
    entry_url = (
        f"https://accounts.google.com/embedded/setup/v2/android"
        f"?source=com.google.android.gm"
        f"&xoauth_display_name=Android+Phone"
        f"&imsi={IMSI}"
        f"&canSk=1"
        f"&mwdm=MWDM_QR"
    )
    resp0 = session.get(entry_url, allow_redirects=True, timeout=30)
    html0 = resp0.text
    log(f"  status={resp0.status_code} url={resp0.url[:80]} len={len(html0)}")

    # ---- Step 0b: Navigate to signup flow ----
    log("[0b] navigating to signup flow...")

    # 从 signin 页面提取 dsh
    dsh0 = extract_token(html0, [
        r'"(S-?\d+:\d+)"',
    ])
    # 更准确的 dsh 提取
    dsh_match = re.search(r'dsh=([^&"]+)', resp0.url)
    if dsh_match:
        dsh0 = dsh_match.group(1)
    if not dsh0:
        dsh_match = re.search(r'"dsh"\s*:\s*"([^"]+)"', html0)
        if dsh_match:
            dsh0 = dsh_match.group(1)
    log(f"  dsh from signin: {dsh0}")

    continue_raw = (
        "https://accounts.google.com/o/android/auth?lang=zh&cc=CN"
        "&langCountry=zh_CN&xoauth_display_name=Android+Device"
        "&tmpl=new_account&source=android&return_user_id=true"
    )
    signup_url = (
        "https://accounts.google.com/lifecycle/flows/signup"
        "?biz=false&canSk=1&cc=cn"
        "&continue=" + urllib.parse.quote(continue_raw, safe="")
        + "&dsh=" + urllib.parse.quote(dsh0 or "", safe="")
        + "&flowName=GlifSetupAndroid"
        + "&hl=zh-Hans-CN"
        + f"&imsi={IMSI}"
        + "&multilogin=1"
        + "&source=com.google.android.gm"
        + "&use_native_navigation=0"
    )
    log(f"  signup_url: {signup_url[:120]}...")
    resp0b = session.get(signup_url, allow_redirects=True, timeout=60)
    html_signup = resp0b.text
    final_url = resp0b.url
    log(f"  status={resp0b.status_code} url={final_url[:100]} len={len(html_signup)}")

    # ---- Extract tokens from signup page ----
    log("[tokens] extracting...")

    fsid = extract_token(html_signup, [
        r'"FdrFJe"\s*:\s*"(-?\d+)"',
        r'f\.sid["\s:=]+(-?\d+)',
        r'FdrFJe.*?(-\d{15,})',
    ])

    at_token = extract_token(html_signup, [
        r'"SNlM0e"\s*:\s*"([^"]+)"',
        r'at\s*[=:]\s*"([^"]+)"',
    ])

    bl = extract_token(html_signup, [
        r'"cfb2h"\s*:\s*"([^"]+)"',
        r'bl\s*[=:]\s*"(boq_[^"]+)"',
    ])

    # TL and dsh from URL
    url_qs = urllib.parse.parse_qs(urllib.parse.urlparse(final_url).query)
    tl = url_qs.get("TL", [""])[0]
    dsh = url_qs.get("dsh", [""])[0]

    log(f"  f.sid: {fsid}")
    log(f"  at: {at_token[:40]}..." if at_token else "  at: NOT FOUND")
    log(f"  bl: {bl}")
    log(f"  TL: {tl[:40]}..." if tl else "  TL: NOT FOUND")
    log(f"  dsh: {dsh}")

    # 如果 token 没找到，dump 一些 HTML 帮助调试
    if not fsid or not at_token:
        log("token extraction failed, dumping page hints...", "WARN")
        # 尝试从页面的 JS 变量中提取
        for pat_name, pat in [
            ("FdrFJe/fsid", r'"FdrFJe":"(-?\d+)"'),
            ("SNlM0e/at", r'"SNlM0e":"([^"]+)"'),
            ("cfb2h/bl", r'"cfb2h":"([^"]+)"'),
            ("fsid alt", r'f\.sid=(-?\d+)'),
            ("at alt", r'\bat=([A-Za-z0-9_-]+:[0-9]+)'),
            ("WIZ_global_data", r'WIZ_global_data\s*=\s*\{'),
        ]:
            m = re.search(pat, html_signup)
            log(f"  {pat_name}: {'FOUND' if m else 'not found'}")

        # 打印 HTML 中包含 "FdrFJe" 或 "SNlM0e" 附近的内容
        for key in ["FdrFJe", "SNlM0e", "cfb2h", "f.sid"]:
            idx = html_signup.find(key)
            if idx >= 0:
                snippet = html_signup[max(0,idx-20):idx+80]
                log(f"  found '{key}' at {idx}: ...{snippet}...")

        if not fsid or not at_token:
            log("FATAL: could not extract session tokens", "ERR")
            return None

    # ---- Step 1: Page init (name page) ----
    log("[1] name page init (MjyMj)...")
    reqid += 1
    resp1, _ = batchexecute(
        session, "MjyMj",
        json.dumps([1, 2, [None, None, None, None, None, None, None, 1, 0, 1, "", None, None, 1, 1, 2]]),
        "/lifecycle/steps/signup/name", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp1.status_code}")

    # ---- Step 2: Submit name (E815hb) ----
    log(f"[2] submitting name: {first} {last} (E815hb)...")
    reqid += 1
    resp2, result2 = batchexecute(
        session, "E815hb",
        json.dumps([first, last, None, None, None, [], None, 1]),
        "/lifecycle/steps/signup/name", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp2.status_code} result={result2[:80] if result2 else 'None'}")
    if result2 and "birthdaygender" in result2:
        log("  → next: birthdaygender")

    # ---- Step 3: Birthday page init (ink9M) ----
    log("[3] birthday page init (ink9M)...")
    reqid += 1
    resp3, result3 = batchexecute(
        session, "ink9M",
        json.dumps([]),
        "/lifecycle/steps/signup/birthdaygender", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp3.status_code}")

    # ---- Step 4: Submit birthday + gender (eOY7Bb) ----
    log(f"[4] submitting birthday: {year}-{month:02d}-{day:02d} (eOY7Bb)...")
    continue_url = "https://accounts.google.com/o/android/auth?lang=zh&cc=CN&langCountry=zh_CN&xoauth_display_name=Android+Device&tmpl=new_account&source=android&return_user_id=true"

    # 真机抓包结构(gmail_recapture.flow eOY7Bb)：
    #   [7] = [BotGuard_token, null, [metadata, path, 1, 0], null, null, [null, 2]]
    #   [7][0]=BotGuard token(2743字符,JS生成)  [7][2][0]=74字符metadata(JS生成)
    #   注意：真机这步 [7][5]=[null,2]，不含 reCAPTCHA token
    # 纯 HTTP 下两个 token 为 None；浏览器方案会经 botguard_token/botguard_meta 注入
    bg_token = (botguard.get("eOY7Bb_token") if botguard else None)
    bg_meta = (botguard.get("eOY7Bb_meta") if botguard else None)

    reqid += 1
    birthday_payload = [
        [year, month, day],
        1,  # gender: 1=male
        None, None, None, None,
        [None, None, continue_url, None, "1"],
        [
            bg_token,                                                     # [7][0] BotGuard token
            None,
            [bg_meta, "/lifecycle/steps/signup/birthdaygender", 1, 0],   # [7][2] [metadata, path, 1, 0]
            None, None,
            [None, 2],                                                    # [7][5] 真机就是 [null,2]
        ],
    ]
    resp4, result4 = batchexecute(
        session, "eOY7Bb",
        json.dumps(birthday_payload),
        "/lifecycle/steps/signup/birthdaygender", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp4.status_code} result={result4[:80] if result4 else 'None'}")
    if result4 and "username" in result4:
        log("  → next: username")

    # ---- Step 5: Username page init (xdYwpe) ----
    log("[5] username page init (xdYwpe)...")
    reqid += 1
    resp5, result5 = batchexecute(
        session, "xdYwpe",
        json.dumps([1]),
        "/lifecycle/steps/signup/username", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp5.status_code}")

    # Parse suggested usernames from response
    suggested_username = None
    if result5:
        try:
            data5 = json.loads(result5)
            if isinstance(data5, list) and len(data5) > 0:
                suggested = data5[0] if isinstance(data5[0], str) else None
                if suggested:
                    suggested_username = suggested
                    log(f"  suggested username: {suggested_username}")
        except Exception:
            pass

    username = suggested_username or f"{first.lower()}{last.lower()}{random.randint(100, 9999)}"
    log(f"  using username: {username}")

    # ---- Step 6: Select username (NHJMOd) ----
    log(f"[6] selecting username: {username} (NHJMOd)...")
    reqid += 1
    resp6, result6 = batchexecute(
        session, "NHJMOd",
        json.dumps([username, 0, 0, None, [None, None, None, None, 1, 2726], 0, 40]),
        "/lifecycle/steps/signup/username", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp6.status_code} result={result6[:80] if result6 else 'None'}")
    if result6 and "password" in result6:
        log("  → next: password")

    # ---- Step 7: Password page init (dOJftd) ----
    log("[7] password page init (dOJftd)...")
    reqid += 1
    resp7, result7 = batchexecute(
        session, "dOJftd",
        json.dumps([None, None, None, None, None, None,
                    [None, None, continue_url, None, "1"]]),
        "/lifecycle/steps/signup/password", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp7.status_code}")

    # ---- Step 8: Submit password (ZNd7Td) ----
    log(f"[8] submitting password (ZNd7Td)...")

    # 真机抓包结构(gmail_recapture.flow ZNd7Td)：
    #   [password, [BotGuard_token, null, [metadata, path, 1, 0], null, null, [null, 2]]]
    #   同 eOY7Bb 的 [7] 块同构；[1][5]=[null,2] 无 reCAPTCHA
    bg_token8 = (botguard.get("ZNd7Td_token") if botguard else None)
    bg_meta8 = (botguard.get("ZNd7Td_meta") if botguard else None)

    reqid += 1
    password_payload = [
        pw,
        [
            bg_token8,                                              # [1][0] BotGuard token
            None,
            [bg_meta8, "/lifecycle/steps/signup/password", 1, 0],  # [1][2] [metadata, path, 1, 0]
            None, None,
            [None, 2],                                              # [1][5]
        ],
    ]
    resp8, result8 = batchexecute(
        session, "ZNd7Td",
        json.dumps(password_payload),
        "/lifecycle/steps/signup/password", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp8.status_code} result={result8[:80] if result8 else 'None'}")

    # ---- Step 9: Silent assertion (GAYtYd) ----
    log("[9] silent assertion (GAYtYd)...")
    reqid += 1
    resp9, result9 = batchexecute(
        session, "GAYtYd",
        json.dumps([]),
        "/lifecycle/steps/signup/silentassertion", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp9.status_code}")

    # ---- Step 10: Silent assertion timeout (dkLoKc) ----
    log("[10] assertion timeout → SMS (dkLoKc)...")
    reqid += 1
    resp10, result10 = batchexecute(
        session, "dkLoKc",
        json.dumps([4]),
        "/lifecycle/steps/signup/silentassertion", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp10.status_code} result={result10[:80] if result10 else 'None'}")
    if result10 and "startmtsmsidv" in result10:
        log("  → next: SMS verification")

    # ---- Step 11: SMS init (IjJvHe) ----
    log("[11] SMS page init (IjJvHe)...")
    reqid += 1
    resp11, result11 = batchexecute(
        session, "IjJvHe",
        json.dumps([]),
        "/lifecycle/steps/signup/startmtsmsidv", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    log(f"  status={resp11.status_code}")

    # ---- Steps 12-14: 手机验证（取号→提交→收码，号不行就取消换新号重试）----
    proj = os.environ.get("SMS_PROJECT_ID_GMAIL", "")
    hero_svc = os.environ.get("HERO_SMS_SERVICE_GMAIL", "")
    max_price = os.environ.get("SMS_MAXPRICE_GMAIL", "0")
    blacklist = tuple(
        c.strip() for c in os.environ.get("SMS_COUNTRY_BLACKLIST_GMAIL", "").split(",") if c.strip()
    )
    max_tries = int(os.environ.get("SMS_MAX_TRIES", "30"))  # 拒号秒切，可多试
    code_wait = int(os.environ.get("SMS_CODE_WAIT", "90"))  # 被接受的号等码时长
    hero_min_active = 122  # hero-sms 最短激活期 120s，到点才能退号
    # hero-sms 轮换国家(sms-activate ID)：泰52(抓包验证可用) 印尼6 菲4 越10 巴西73 印22 墨54 尼19 孟60 马7
    # 避开最便宜的肯尼亚(8)等被 Google 整段拉黑的号池
    hero_countries = [c.strip() for c in os.environ.get(
        "SMS_HERO_COUNTRIES", "52,6,4,10,73,22,54,19,60,7").split(",") if c.strip()]

    # 延迟释放队列：(pkey, 占用时间戳)。hero 号不到 120s 不能退，攒着到点批量退
    pending_release = []

    def _sweep_release(force=False):
        nonlocal pending_release
        keep = []
        for pk, ts in pending_release:
            if force or (time.time() - ts) >= hero_min_active:
                try:
                    sms_client.release(pk)
                except Exception:
                    pass
            else:
                keep.append((pk, ts))
        pending_release = keep

    def _defer_release(pk):
        """firefox 号立即退；hero 号攒进队列等满 120s 再退。"""
        if str(pk).startswith("hero_"):
            pending_release.append((pk, time.time()))
        else:
            try:
                sms_client.release(pk)
            except Exception:
                pass

    def _fail_dict(status):
        return {
            "status": status,
            "email": f"{username}@gmail.com", "username": username,
            "password": pw, "name": f"{first} {last}",
            "birthday": f"{year}-{month:02d}-{day:02d}",
        }

    def submit_phone(e164, iso):
        """rxubAb 提交号 + Ruteu 初始化验证页。返回 rxubAb result。"""
        nonlocal reqid
        reqid += 1
        r12, res12 = batchexecute(
            session, "rxubAb",
            json.dumps([[[e164, iso], None, 145, continue_url,
                         [continue_url, None, "com.google.android.gm"]]]),
            "/lifecycle/steps/signup/startmtsmsidv", fsid, bl, at_token, reqid, tl=tl, dsh=dsh)
        log(f"  [12] 提交 {e164} ({iso}) → status={r12.status_code} result={res12[:50] if res12 else 'None'}")
        if os.environ.get("GMAIL_DEBUG"):
            log(f"  [debug] rxubAb raw: {r12.text[:500]}")
        # 判据（抓包确认）：rxubAb 响应含 "verifyphone" = 号可用、已发码；
        # 空响应 = Google 拒号、不会发码 → 立刻换号，不等待
        accepted = bool(res12 and "verifyphone" in res12.lower())
        if accepted:
            reqid += 1
            batchexecute(session, "Ruteu", json.dumps([]),
                         "/lifecycle/steps/signup/verifyphone/idv", fsid, bl, at_token, reqid, tl=tl, dsh=dsh)
        return res12, accepted

    def submit_code(c):
        nonlocal reqid
        reqid += 1
        r14, res14 = batchexecute(
            session, "ZN031c",
            json.dumps([c, 2, 99, None, [continue_url, None, "com.google.android.gm"], continue_url]),
            "/lifecycle/steps/signup/verifyphone/idv", fsid, bl, at_token, reqid, tl=tl, dsh=dsh)
        log(f"  [14] 提交码 {c} → status={r14.status_code} result={res14[:50] if res14 else 'None'}")
        return res14

    verified = False

    # -------- 自动接码：换号重试循环 --------
    if auto_sms and sms_client and not phone_number:
        if not (proj or hero_svc):
            log("auto_sms 开启但 SMS_PROJECT_ID_GMAIL/HERO_SMS_SERVICE_GMAIL 未配置", "WARN")
            return _fail_dict("need_phone")
        no_number_streak = 0
        for attempt in range(1, max_tries + 1):
            _sweep_release()  # 退掉已满 120s 的旧号，回收余额
            pkey = None
            try:
                hc = hero_countries[(attempt - 1) % len(hero_countries)] if (hero_svc and hero_countries) else None
                hero_op = os.environ.get("SMS_HERO_OPERATOR", "") or None
                hero_fixed = os.environ.get("SMS_HERO_FIXED_PRICE", "").lower() in ("1", "true", "yes")
                log(f"[sms] 取号 (第 {attempt}/{max_tries} 次, 国家={hc or 'auto'}{('/'+hero_op) if hero_op else ''}{' fixed$'+max_price if hero_fixed else ''})...")
                raw_phone, raw_cc, pkey = sms_client.get_phone(
                    proj, hero_svc, country_blacklist=blacklist, max_price=max_price,
                    hero_country=hc, hero_operator=hero_op, hero_fixed_price=hero_fixed)
                full = (raw_cc + raw_phone) if raw_cc else raw_phone
                e164, iso = _split_intl_phone(full)
                log(f"[sms] 号: {e164} (pkey={pkey})")
                no_number_streak = 0
            except Exception as e:
                no_number_streak += 1
                log(f"[sms] 取号失败({no_number_streak}): {e}", "WARN")
                if no_number_streak >= 3:
                    log("[sms] 连续取号失败(多半余额耗尽/无号)，停止", "WARN")
                    break
                time.sleep(2)
                continue

            res12, accepted = submit_phone(e164, iso)
            always_wait = os.environ.get("SMS_ALWAYS_WAIT")  # 调试：空响应也强制等码，验证判据
            if not accepted and not always_wait:
                log(f"[sms] {e164} 不可用(Google 未发码)，秒切下一个", "WARN")
                _defer_release(pkey)
                continue

            if accepted:
                log(f"[sms] ✓ {e164} 已被接受，Google 发码中，等待 (≤{code_wait}s)...", "OK")
            else:
                log(f"[sms] ⚠ {e164} rxubAb 返回空(理论应拒)，但按测试强制等码 (≤{code_wait}s)...", "WARN")
            code = sms_client.get_code(pkey, max_wait=code_wait, interval=4)
            if not code:
                log(f"[sms] {e164} 接受了但 {code_wait}s 没收到码，换号", "WARN")
                _defer_release(pkey)
                continue

            res14 = submit_code(code)
            low = (res14 or "").lower()
            if res14 and ("confirmation" in low or "termsofservice" in low or "success" in low):
                log(f"  → 手机验证成功! ({e164})", "OK")
                verified = True
                break
            if any(k in low for k in ("incorrect", "invalid", "wrong", "expired")):
                log(f"[sms] 验证码被拒，换号重试", "WARN")
                _defer_release(pkey)
                continue
            # result=None 等含糊情况：当作已推进（与前几步同理）
            log("  step14 未明确返回 confirmation，按已推进继续", "WARN")
            verified = True
            break

        if not verified:
            log(f"[sms] {max_tries} 次都没过，放弃；清退占用号", "WARN")
            _sweep_release(force=True)
            return _fail_dict("phone_failed")
        _sweep_release(force=True)  # 成功后也把残留旧号退掉

    # -------- 手动号 / 交互输码 --------
    else:
        if not phone_number:
            log("需要手机号码。用 --phone 提供，或 --auto-sms 自动接码", "WARN")
            return _fail_dict("need_phone")
        e164, iso = _split_intl_phone(phone_number)
        submit_phone(e164, iso)
        code = sms_code or input("输入收到的验证码: ").strip()
        res14 = submit_code(code)
        verified = bool(res14 and "confirmation" in (res14 or "").lower()) or True

    # ---- Step 15: Confirmation (kAcJN) ----
    log("[15] confirmation (kAcJN)...")
    reqid += 1
    resp15, result15 = batchexecute(
        session, "kAcJN",
        json.dumps([]),
        "/lifecycle/steps/signup/confirmation", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )
    email = None
    if result15:
        m = re.search(r'([a-zA-Z0-9.]+@gmail\.com)', result15)
        if m:
            email = m.group(1)
            log(f"  email: {email}")

    # ---- Step 16: Confirm → terms (ACzr9e) ----
    log("[16] confirm → terms (ACzr9e)...")
    reqid += 1
    resp16, _ = batchexecute(
        session, "ACzr9e",
        json.dumps([]),
        "/lifecycle/steps/signup/confirmation", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )

    # ---- Step 17+: Terms of service (simplified) ----
    log("[17] accepting terms...")
    for rpc, payload in [
        ("wrWg8b", json.dumps([])),
        ("j67kh", json.dumps([[None, 1]])),
        ("j67kh", json.dumps([[None, None, 1]])),
        ("j67kh", json.dumps([[None, None, None, 1]])),
    ]:
        reqid += 1
        batchexecute(session, rpc, payload,
                     "/lifecycle/steps/signup/termsofservice", fsid, bl, at_token, reqid)

    log("[18] finalizing account...")
    reqid += 1
    resp_final, result_final = batchexecute(
        session, "hAMCqc",
        json.dumps([[]]),  # simplified - original has hash list
        "/lifecycle/steps/signup/termsofservice", fsid, bl, at_token, reqid,
        tl=tl, dsh=dsh,
    )

    if email:
        log(f"注册成功! email={email} password={pw}", "OK")
    else:
        log("注册流程完成，但未确认邮箱", "WARN")

    return {
        "status": "success" if email else "unknown",
        "email": email or f"{username}@gmail.com",
        "username": username,
        "password": pw,
        "name": f"{first} {last}",
        "birthday": f"{year}-{month:02d}-{day:02d}",
    }


# ======================== Main ========================

def main():
    parser = argparse.ArgumentParser(description="Gmail protocol registration")
    parser.add_argument("--first", type=str, help="First name")
    parser.add_argument("--last", type=str, help="Last name")
    parser.add_argument("--password", type=str, help="Password")
    parser.add_argument("--phone", type=str, help="Phone number (+CCNUMBER)")
    parser.add_argument("--proxy", type=str, help="Proxy (socks5://... or http://...)")
    parser.add_argument("--auto-sms", action="store_true", help="自动接码完成手机验证")
    parser.add_argument("--no-rotate", action="store_true", help="不轮换代理 sid")
    args = parser.parse_args()

    proxy = args.proxy
    if not proxy and os.environ.get("OUTLOOK_PROXIES"):
        proxy = os.environ.get("OUTLOOK_PROXIES", "").splitlines()[0]
    # 轮换 sid 换新 IP + 强制 socks5h(远端 DNS)，避免旧 sid 失效 / 本地 DNS 握手断
    if proxy and not args.no_rotate:
        try:
            from outlook_reg_loop import rotate_proxy_sid
            proxy = rotate_proxy_sid(proxy)
        except Exception:
            pass
    if proxy and proxy.startswith("socks5://"):
        proxy = proxy.replace("socks5://", "socks5h://", 1)

    result = register_gmail(
        first_name=args.first,
        last_name=args.last,
        password=args.password,
        proxy_str=proxy,
        phone_number=args.phone,
        auto_sms=args.auto_sms,
    )

    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result and result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
