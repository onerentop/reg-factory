# -*- coding: utf-8 -*-
"""
register_gmail_hybrid.py — 混合方案：浏览器铸 BotGuard + HTTP 跑手机验证。

为什么混合（gmail_recapture.flow 真机抓包逐字段证明）：
  生日(eOY7Bb)/密码(ZNd7Td) 两步要 JS 生成的 BotGuard token([7][0] 2743字符)
  + metadata([7][2][0] 74字符)，纯 HTTP 造不出 → 会话不可信 → 手机号全被拒。
  而 rxubAb(提交手机号) 本身不带 BotGuard，只要会话被信任即可。

流程：
  [浏览器] 打开 Android 注册流 → 姓名→生日→用户名→密码（真浏览器原生铸 BotGuard）
           → 到手机页，提取 cookies + f.sid/at/dsh/TL/bl
  [HTTP]   用该可信会话跑 SMS 换号重试（复用 register_gmail_protocol 的 batchexecute + 接码）

用法：
  python register_gmail_hybrid.py --auto-sms
  python register_gmail_hybrid.py --manual            # 浏览器里手动填，脚本只接管手机步
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import re
import string
import sys
import time
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: F401  (loads .env)
from common.browser_provider import get_browser_provider

# 复用纯协议里的工具
import register_gmail_protocol as P

try:
    from outlook_reg_loop import rotate_proxy_sid
except Exception:
    def rotate_proxy_sid(p):
        return p

IMSI = "460009188843340"
CONTINUE_RAW = (
    "https://accounts.google.com/o/android/auth?lang=zh&cc=CN"
    "&langCountry=zh_CN&xoauth_display_name=Android+Device"
    "&tmpl=new_account&source=android&return_user_id=true"
)


def log(msg, level="INFO"):
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def rand_str(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def build_signup_url(dsh=""):
    return (
        "https://accounts.google.com/lifecycle/flows/signup"
        "?biz=false&canSk=1&cc=cn"
        "&continue=" + urllib.parse.quote(CONTINUE_RAW, safe="")
        + "&dsh=" + urllib.parse.quote(dsh, safe="")
        + "&flowName=GlifSetupAndroid&hl=zh-Hans-CN"
        + f"&imsi={IMSI}&multilogin=1&source=com.google.android.gm&use_native_navigation=0"
    )


# ======================== 浏览器：走到手机页 ========================

async def click_next(page):
    """点“下一步/Next”按钮（jsname=LgbsSe 在各步一致）。"""
    for sel in [
        'button[jsname="LgbsSe"]',
        'button:has-text("下一步")', 'button:has-text("Next")',
        'button[type="submit"]',
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.count() and await btn.is_visible():
                await btn.click(timeout=4000)
                return True
        except Exception:
            continue
    return False


async def fill_first(page, selectors, value, timeout=12000):
    """按多个候选选择器填第一个可见输入框。"""
    end = time.time() + timeout / 1000
    while time.time() < end:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    await loc.fill(value, timeout=3000)
                    return True
            except Exception:
                continue
        await asyncio.sleep(0.5)
    return False


async def _on_page(page, keyword):
    """当前 URL 是否含某 step 关键字。"""
    return keyword in page.url


async def wait_url(page, keyword, timeout=15):
    """轮询直到 URL 含 keyword。"""
    import time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        if keyword in page.url:
            return True
        await asyncio.sleep(0.5)
    return keyword in page.url


async def is_visible(page, sel, timeout=2.0):
    import time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                return True
        except Exception:
            pass
        await asyncio.sleep(0.3)
    return False


async def drive_to_phone(page, profile):
    """姓名→生日→用户名→密码 全自动（选择器经 DOM 实测）。失败退回人工轮询。"""
    first = random.choice(P.FIRST_NAMES)
    last = random.choice(P.LAST_NAMES)
    pw = f"Gm{rand_str(6)}!{random.randint(10,99)}"
    year = random.randint(1988, 1998)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    profile.update({"first": first, "last": last, "pw": pw,
                    "year": year, "month": month, "day": day})
    log(f"[browser] 资料: {first} {last} / {pw} / {year}-{month:02d}-{day:02d}")

    # ---- 姓名 ----
    for _name_try in range(3):
        if await fill_first(page, ['input[name=firstName]', 'input#firstName'], first):
            await fill_first(page, ['input[name=lastName]', 'input#lastName'], last, 4000)
            await click_next(page)
            log("[browser] 姓名已提交")
            await wait_url(page, "birthdaygender", 25)
            await asyncio.sleep(1.5)
            break
        else:
            log(f"[browser] 姓名填充失败({_name_try+1}/3)，刷新重试", "WARN")
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

    # ---- 生日性别 ----
    for _bday_try in range(3):
        if await fill_first(page, ['input#day', 'input[name=day]'], str(day), 20000):
            await fill_first(page, ['input#year', 'input[name=year]'], str(year), 4000)
            # 月份(Material 下拉)：点开 → 按文本"N 月"精确点
            try:
                await page.click('#month', timeout=3000)
                await asyncio.sleep(0.6)
                await page.get_by_role('option', name=f'{month} 月', exact=True).click(timeout=3000)
            except Exception as e:
                log(f"[browser] 月份选择失败: {e}", "WARN")
            await asyncio.sleep(0.4)
            # 性别 → 男
            try:
                await page.click('#gender', timeout=2500)
                await asyncio.sleep(0.6)
                await page.get_by_role('option', name='男', exact=True).click(timeout=3000)
            except Exception as e:
                log(f"[browser] 性别选择失败: {e}", "WARN")
            await asyncio.sleep(0.4)
            await click_next(page)
            log("[browser] 生日已提交")
            await wait_url(page, "username", 25)
            break
        else:
            log(f"[browser] 生日填充失败({_bday_try+1}/3)，刷新重试", "WARN")
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

    # ---- 用户名（两变体：输入框 / 选择列表）----
    await wait_url(page, "username", 25)
    await asyncio.sleep(1.5)
    for uname_try in range(4):
        if not await _on_page(page, "username"):
            break
        # 选择变体：先点"创建您自己的 Gmail 邮箱"单选，露出输入框
        if not await is_visible(page, 'input[name=Username]', 1.5):
            for sel in ['div[role=radio]:has-text("创建")', 'text=创建您自己的',
                        '[role=radio]:last-child', '[role=radio]']:
                try:
                    r = page.locator(sel).last
                    if await r.count() and await r.is_visible():
                        await r.click(timeout=2500)
                        await asyncio.sleep(1)
                        break
                except Exception:
                    continue
        uname = f"{first.lower()}{last.lower()}{random.randint(1000, 99999)}"
        if await fill_first(page, ['input[name=Username]'], uname, 6000):
            profile["username"] = uname
            await click_next(page)
            log(f"[browser] 用户名 {uname} 已提交")
            await asyncio.sleep(3)
            if not await _on_page(page, "username"):
                break
            log("[browser] 用户名可能被占，换一个重试", "WARN")
        else:
            log("[browser] 用户名输入框未出现", "WARN")
            break

    # ---- 密码（单框，无确认）----
    await wait_url(page, "password", 25)
    await asyncio.sleep(1)
    for _pw_try in range(3):
        if await fill_first(page, ['input[name=Passwd]', 'input[type=password]'], pw):
            await click_next(page)
            log("[browser] 密码已提交")
            await asyncio.sleep(3)
            break
        else:
            log(f"[browser] 密码填充失败({_pw_try+1}/3)，刷新重试", "WARN")
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
    return True


async def wait_phone_page(page, max_wait=240):
    """轮询直到到达手机验证页(URL 含 phone/smsidv)，支持人工补完。遇 error 提前退出。"""
    end = time.time() + max_wait
    while time.time() < end:
        u = page.url
        if any(k in u for k in ("verifyphone", "startmtsmsidv", "phone")):
            return True
        if "unknownerror" in u or "error" in u.split("/")[-1].lower():
            log(f"[browser] 注册过程报错: {u.split('/')[-1][:30]}", "WARN")
            return False
        await asyncio.sleep(1.5)
    return False


# ======================== HTTP：用浏览器会话跑手机验证 ========================

# ======================== 浏览器手机验证 + 建号收尾 ========================

def _svc_acquire(provider, country, max_price, fixed, service="go"):
    """走 services sms_service 取号。返回 (phone, order_id) 或 (None, None)。"""
    import requests as _r
    try:
        resp = _r.post("http://localhost:8001/sms/number/acquire", json={
            "service": service, "country": str(country), "provider": provider,
            "max_price": str(max_price), "fixed_price": bool(fixed),
        }, timeout=30, proxies={"http": None, "https": None})
        d = resp.json().get("data") or {}
        return d.get("phone_number"), d.get("order_id")
    except Exception as e:
        log(f"  [svc-sms] acquire err: {e}", "WARN")
        return None, None


def _svc_code(order_id, max_wait=180):
    """走 services sms_service 收码。返回 code 或 None。"""
    import requests as _r
    try:
        resp = _r.get(f"http://localhost:8001/sms/number/{order_id}/code",
                      params={"timeout": max_wait}, timeout=max_wait + 10,
                      proxies={"http": None, "https": None})
        return (resp.json().get("data") or {}).get("code")
    except Exception as e:
        log(f"  [svc-sms] code err: {e}", "WARN")
        return None


def _svc_cancel(order_id):
    """走 services sms_service 释放号（取消订单）。"""
    import requests as _r
    try:
        _r.post(f"http://localhost:8001/sms/number/{order_id}/cancel",
                timeout=15, proxies={"http": None, "https": None})
    except Exception as e:
        log(f"  [svc-sms] cancel err: {e}", "WARN")


async def browser_phone_and_finalize(page, profile, ctx=None, profile_id=None, sms_config=None):
    """全浏览器：手机换号重试 + 收码 + 条款同意 + 建号（同一会话，BotGuard 原生）。
    sms_config 含 provider 时走 services sms_service 取号/收码/释放，否则用旧 common/sms.py。"""
    import re as _re
    sms = P.sms_client
    hero_svc = os.environ.get("HERO_SMS_SERVICE_GMAIL", "go")
    max_price = os.environ.get("SMS_MAXPRICE_GMAIL", "0.1024")
    hero_country = (os.environ.get("SMS_HERO_COUNTRIES", "52").split(",")[0]).strip()
    fixed = os.environ.get("SMS_HERO_FIXED_PRICE", "true").lower() in ("1", "true", "yes")
    max_tries = int(os.environ.get("SMS_MAX_TRIES", "10"))
    code_wait = int(os.environ.get("SMS_CODE_WAIT", "90"))
    phone_used = None
    consecutive_reject = 0

    # services 接码配置（sms_config 有 provider 时优先走 services sms_service）
    sms_config = sms_config or {}
    use_svc = bool(sms_config.get("provider"))
    svc_provider = sms_config.get("provider", "")
    svc_country = sms_config.get("country", hero_country)
    svc_maxprice = sms_config.get("max_price", max_price)
    svc_fixed = sms_config.get("fixed_price", fixed)

    # 自动探测国家（auto_probe 开 + 走 services）：按价升序候选序列逐国试，
    # 收到码记可用、失败记冷却，结束回写可用库。
    auto_probe = bool(sms_config.get("auto_probe")) and use_svc
    probe = None
    seq = []
    if auto_probe:
        import time as _time
        from common.country_probe import (
            build_probe_sequence, mark_available, mark_failed, probe_load, probe_save, probe_prices,
        )
        probe = probe_load()
        _prices = probe_prices(svc_provider)
        seq = build_probe_sequence(_prices, probe, svc_maxprice, int(_time.time()))
        log(f"[probe] 候选国家 {len(seq)} 个(≤{svc_maxprice}): {[s['country'] for s in seq[:8]]}")
        if not seq:
            log("[probe] 无候选国家(都在冷却或超价)，放弃", "WARN")
            return None

    def _release(pk):
        if not pk:
            return
        if str(pk).startswith("svc_"):
            _svc_cancel(pk[4:])
        else:
            try:
                sms.release(pk)
            except Exception:
                pass

    for attempt in range(1, max_tries + 1):
        pkey = None
        if auto_probe:
            if attempt - 1 >= len(seq):
                log("[probe] 候选国家已试完", "WARN")
                break
            _cur = seq[attempt - 1]
            cur_country, cur_name, cur_price = _cur["country"], _cur["name"], _cur["price"]
        else:
            cur_country = svc_country
        try:
            if use_svc:
                _ctag = f"{cur_name} {cur_country} ${cur_price}" if auto_probe else f"国家={cur_country}"
                log(f"[sms] 取号 services({svc_provider}, {_ctag}, 第 {attempt}/{max_tries})...")
                _ph, _oid = _svc_acquire(svc_provider, cur_country, svc_maxprice, svc_fixed, service=hero_svc)
                if not _ph:
                    raise RuntimeError("services 取号无号")
                pkey = f"svc_{_oid}"
                e164, _ = P._split_intl_phone(_ph)
                log(f"[sms] 号(svc): {e164}")
            else:
                log(f"[sms] 取号 (第 {attempt}/{max_tries}, 国家={hero_country})...")
                raw, cc, pkey = sms.get_phone(
                    "", hero_svc, max_price=max_price,
                    hero_country=hero_country, hero_fixed_price=fixed)
                full = (cc + raw) if cc else raw
                e164, _ = P._split_intl_phone(full)
                log(f"[sms] 号: {e164}")
        except Exception as e:
            log(f"[sms] 取号失败: {e}", "WARN")
            if auto_probe and probe is not None:
                mark_failed(probe, cur_country, f"取号失败:{str(e)[:30]}", int(_time.time()))
            await asyncio.sleep(2)
            continue

        # 填号码(清空再填)
        try:
            inp = page.locator("input#phoneNumberId, input[type=tel]").first
            await inp.fill("", timeout=3000)
            await inp.fill(e164, timeout=4000)
        except Exception as e:
            log(f"[sms] 填号失败: {e}", "WARN")
            _release(pkey)
            continue
        await click_next(page)
        await asyncio.sleep(5)

        # 判定：是否进入收码页(input#code 出现 = 号被接受)
        if await is_visible(page, "input#code, input[name=code]", 3):
            consecutive_reject = 0
            log(f"[sms] {e164} 被接受，等码 (≤{code_wait}s)...")
            if pkey and str(pkey).startswith("svc_"):
                code = _svc_code(pkey[4:], max_wait=code_wait)
            else:
                code = sms.get_code(pkey, max_wait=code_wait, interval=4)
            if not code:
                log(f"[sms] {e164} 没收到码，换号", "WARN")
                _release(pkey)
                if auto_probe and probe is not None:
                    mark_failed(probe, cur_country, "无码", int(_time.time()))
                await page.go_back(timeout=10000)
                await asyncio.sleep(2)
                continue
            # 填码提交
            try:
                ci = page.locator("input#code, input[name=code]").first
                await ci.fill(code, timeout=4000)
            except Exception as e:
                log(f"[sms] 填码失败: {e}", "WARN")
                continue
            await click_next(page)
            await asyncio.sleep(5)
            phone_used = e164
            if auto_probe and probe is not None:
                mark_available(probe, cur_country, cur_name, cur_price, int(_time.time()))
            log(f"[sms] 验证码已提交! ({e164} 码={code})", "OK")
            break
        else:
            # 没进收码页——看页面到底显示了什么
            consecutive_reject += 1
            try:
                diag = (await page.inner_text("body"))[:80].replace("\n", " ")
            except Exception:
                diag = page.url[:50]
            log(f"[sms] {e164} 不可用，换号 | 页面: {diag}", "WARN")
            _release(pkey)
            if auto_probe and probe is not None:
                mark_failed(probe, cur_country, diag[:40], int(_time.time()))
            if consecutive_reject >= 5:
                log("[sms] 连续5个号被拒，会话可能不被信任，放弃", "WARN")
                break
            # 可能还在手机页(号被拒不跳页)或出错页，确保回到手机页
            if "verifyphone" in page.url or "error" in page.url:
                try: await page.go_back(timeout=8000)
                except Exception: pass
                await asyncio.sleep(2)
            continue

    if auto_probe and probe is not None:
        probe_save(probe)
        log(f"[probe] 回写可用库: 可用{len(probe.get('available', []))}国 / 冷却{len(probe.get('failed', {}))}国")

    if not phone_used:
        log("[sms] 重试用尽，手机验证未通过", "WARN")
        return None

    # ---- 收尾：确认页 → 条款 → 建号 ----
    # 真机抓包：用户只做 2 次点击(确认页"下一步" + 条款页"我同意")。
    # 点完"我同意"后 Google JS 自动跑 hAMCqc→d6fbce(BotGuard)→ihzRS 建号。
    # 关键：不能干扰（不滚动/不读DOM/不执行JS），否则 d6fbce 异常→unknownerror。
    email = f"{profile.get('username','?')}@gmail.com"
    await asyncio.sleep(2)

    # Step1: 确认页 → 点"下一步"
    log("[finalize] 确认页...")
    await click_next(page)
    await asyncio.sleep(5)

    # Step2: 条款页 → 等按钮出现 → 滚到底(纯键盘) → 点"我同意"
    log("[finalize] 条款页...")
    agree_clicked = False
    for _tos_try in range(6):
        try:
            await page.keyboard.press("End")
            await asyncio.sleep(1)
        except Exception:
            pass
        for sel in ['button:has-text("我同意")', 'button:has-text("I agree")']:
            try:
                b = page.locator(sel).last
                if await b.count() and await b.is_visible():
                    await b.click(timeout=5000)
                    agree_clicked = True
                    log("[finalize] 已点击 [我同意]")
                    break
            except Exception:
                continue
        if agree_clicked:
            break
        await asyncio.sleep(3)
    if not agree_clicked:
        log("[finalize] 未找到'我同意'按钮（等了~24秒）", "WARN")

    # Step3: 纯等 Google 建号（不做任何操作，等 URL 离开 termsofservice）
    log("[finalize] 等待 Google 建号（不干扰，最多90秒）...")
    tos_url = page.url
    for _w in range(60):
        cur = page.url
        if cur != tos_url:
            break
        await asyncio.sleep(1.5)

    final_url = page.url
    log(f"[finalize] 终止页: {final_url[:75]}")

    # unknownerror 是结构性的（缺 DroidGuard），但账号已建成。直接 SMTP 验证。
    final_url = page.url
    acct_email = email or f"{profile.get('username','?')}@gmail.com"
    if "unknownerror" in final_url:
        log("[finalize] unknownerror（正常，缺 DroidGuard），SMTP 验证账号...")
    done = smtp_verify(acct_email)
    if done:
        log(f"[finalize] SMTP 确认账号存在: {acct_email}", "OK")
    elif "unknownerror" not in final_url and "signup" not in final_url:
        done = True
    else:
        log(f"[finalize] 账号未建成(SMTP 550)，终止页: {final_url[:70]}", "WARN")
    acct = {
        "email": email or f"{profile.get('username','?')}@gmail.com",
        "password": profile.get("pw", "?"),
        "phone": phone_used,
        "name": f"{profile.get('first','')} {profile.get('last','')}",
        "birthday": f"{profile.get('year')}-{profile.get('month'):02d}-{profile.get('day'):02d}",
        "profile_id": profile_id,
    }
    if done:
        save_account(acct)
        log(f"账号建成: {acct['email']} / {acct['password']} (手机 {acct['phone']})", "OK")
        # 在同一窗口重新登录（同IP同指纹，不触发验证）→ 窗口保留已登录态
        if ctx:
            await _relogin_same_window(page, acct["email"], acct["password"])
        return acct
    log(f"[finalize] 未确认成功，终止页: {page.url[:80]}", "WARN")
    return None


async def _relogin_same_window(page, email, password):
    """unknownerror 后在同一窗口登录（同IP同指纹→不触发验证）→ 窗口保留已登录态。"""
    log("[relogin] 在同窗口重新登录...")
    try:
        await asyncio.wait_for(_do_relogin(page, email, password), timeout=45)
    except asyncio.TimeoutError:
        log("[relogin] 超时(45s)，跳过（账号已建成，不影响）", "WARN")
    except Exception as e:
        log(f"[relogin] 异常: {e}", "WARN")


async def _do_relogin(page, email, password):
    """relogin 实际逻辑（由 _relogin_same_window 包装超时控制）。"""
    await page.goto("https://accounts.google.com/signin/v2/identifier?hl=en&flowName=GlifWebSignIn&flowEntry=ServiceLogin",
                    wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)
    # 邮箱
    for sel in ['input#identifierId', 'input[type=email]']:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=3000)
                await asyncio.sleep(0.3)
                await page.keyboard.type(email, delay=30)
                break
        except Exception:
            continue
    for sel in ['#identifierNext button', 'button[jsname="LgbsSe"]']:
        try:
            b = page.locator(sel).first
            if await b.count() and await b.is_visible():
                await b.click(timeout=4000); break
        except Exception:
            continue
    await asyncio.sleep(5)
    # 密码
    for sel in ['input[type=password]', 'input[name=Passwd]']:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=3000)
                await asyncio.sleep(0.3)
                await page.keyboard.type(password, delay=30)
                break
        except Exception:
            continue
    for sel in ['#passwordNext button', 'button[jsname="LgbsSe"]']:
        try:
            b = page.locator(sel).first
            if await b.count() and await b.is_visible():
                await b.click(timeout=4000); break
        except Exception:
            continue
    await asyncio.sleep(6)
    # 跳过中间页（passkey等）
    for _ in range(3):
        skipped = False
        for sel in ['button:has-text("Not now")', 'button:has-text("暂不")',
                    'button:has-text("跳过")', 'button:has-text("Skip")']:
            try:
                b = page.locator(sel).first
                if await b.count() and await b.is_visible():
                    await b.click(timeout=3000); skipped = True; break
            except Exception:
                continue
        if not skipped:
            break
        await asyncio.sleep(3)
    # 验证登录态
    await page.goto("https://myaccount.google.com/?hl=en", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)
    url = page.url
    if "myaccount.google.com" in url and "about" not in url:
        log(f"[relogin] 登录成功: {url[:55]}")
    else:
        log(f"[relogin] 登录未确认: {url[:55]}", "WARN")


# ======================== 主流程 ========================

def find_working_proxy(base, tries=8):
    """轮换 sid 直到找到能连通 google 的（ixBrowser 代理检测很挑节点）。"""
    for i in range(tries):
        p = rotate_proxy_sid(base)
        ph = p.replace("socks5://", "socks5h://", 1) if p.startswith("socks5://") else p
        try:
            r = requests.get("https://accounts.google.com/generate_204",
                             proxies={"http": ph, "https": ph}, timeout=12)
            if r.status_code == 204:
                log(f"proxy sid#{i} 可用")
                return p  # 返回 socks5:// 形式给 ixBrowser（浏览器自做 DNS）
        except Exception:
            pass
    return None


async def run(args, worker_id=0, save_lock=None):
    prefix = f"W{worker_id}"
    def wlog(msg, level="INFO"):
        log(f"[{prefix}] {msg}", level)

    proxy_base = (os.environ.get("OUTLOOK_PROXIES", "") or "").splitlines()

    bb = get_browser_provider()
    pid = None
    proxy = None
    profile = {}
    sess_info = None
    try:
        for _browser_try in range(3):
            try:
                proxy = find_working_proxy(proxy_base[0]) if proxy_base else None
                if proxy_base and not proxy:
                    wlog("代理不可用，重试...", "WARN")
                    continue
                pid = bb.create_browser(name=f"gmail_{worker_id}", proxy_str=proxy)
                info = bb.open_browser(pid)
                break
            except Exception as e:
                wlog(f"创建窗口失败({_browser_try+1}/3): {e}", "WARN")
                if pid:
                    try: bb.delete_browser(pid)
                    except Exception: pass
                    pid = None
                await asyncio.sleep(2)
        else:
            wlog("3次创建窗口都失败，放弃", "ERR")
            return None

        wlog(f"proxy: {(proxy or 'DIRECT')[:55]}")
        ws = info.get("ws", "")
        wlog(f"cdp: {ws[:55]}")

        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws)
            cxt = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = cxt.pages[0] if cxt.pages else await cxt.new_page()
            # 禁用 passkey 弹窗：覆盖 navigator.credentials，网站 fallback 到密码登录
            await cxt.add_init_script("""
                Object.defineProperty(navigator, 'credentials', {
                    get: () => ({ create: () => Promise.reject('disabled'), get: () => Promise.reject('disabled'), store: () => Promise.reject('disabled') })
                });
            """)

            signup_url = build_signup_url()
            wlog(f"[browser] 打开注册流...")
            await page.goto(signup_url, wait_until="domcontentloaded", timeout=60000)
            wlog(f"[browser] 落地: {page.url[:70]}")

            if not args.manual:
                try:
                    await drive_to_phone(page, profile)
                except Exception as e:
                    wlog(f"[browser] 自动填充异常(转人工): {e}", "WARN")

            wlog("=" * 56)
            wlog("若自动未完成：请在弹出窗口手动走到【手机验证页】停住")
            wlog(f"脚本自动检测手机页并接管。最多等 {args.wait}s")
            wlog("=" * 56)

            if not await wait_phone_page(page, args.wait):
                wlog("未到手机页，放弃", "ERR")
                return None
            wlog("[browser] 已到手机验证页")

            if not args.auto_sms:
                wlog("未开 --auto-sms：到手机页停。", "WARN")
                return None
            acct = await browser_phone_and_finalize(page, profile, ctx=cxt, profile_id=pid)
    finally:
        if pid:
            try:
                bb.close_browser(pid)  # 关闭浏览器（但保留 profile，不删除）
                await asyncio.sleep(1)
                if acct and acct.get("email"):
                    acct["profile_id"] = pid
                    # 窗口改名=邮箱，备注=账户信息
                    try:
                        from ixbrowser_local_api.entities import Profile as _P
                        up = _P()
                        up.profile_id = int(pid)
                        up.name = acct["email"]
                        up.note = f"{acct['password']} | {acct.get('phone','')} | {acct.get('name','')}"
                        bb._call("update_profile", up)
                    except Exception:
                        pass
                elif args.delete_window:
                    bb.delete_browser(pid)  # 失败才删
            except Exception:
                pass
    return acct


def smtp_verify(email, timeout=10):
    """SMTP 探测 Gmail 邮箱是否存在（250=存在, 550=不存在）。"""
    import smtplib
    try:
        s = smtplib.SMTP("gmail-smtp-in.l.google.com", 25, timeout=timeout)
        s.ehlo("verify.local")
        s.mail("test@verify.local")
        code, _ = s.rcpt(email)
        s.quit()
        return code == 250
    except Exception:
        return False  # 网络问题时返回 False（不确定）


def save_account(acct):
    """把账号追加到 accounts_gmail.txt（含 profile_id，用于后续复用窗口免验证登录）。"""
    base = os.path.dirname(os.path.abspath(__file__))
    pid = str(acct.get("profile_id", ""))
    line = "----".join([acct["email"], acct["password"], acct["phone"], acct["name"], acct["birthday"], pid])
    path = os.path.join(base, "accounts_gmail.txt")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        log(f"[save] 凭据 → {path} (profile_id={pid})")
    except Exception as e:
        log(f"[save] 写入失败: {e}", "WARN")


async def _main_async(args):
    sem = asyncio.Semaphore(args.parallel)

    async def worker(i):
        async with sem:
            log("=" * 50)
            log(f"### 第 {i}/{args.count} 个账号 ###")
            log("=" * 50)
            try:
                return await run(args, worker_id=i)
            except Exception as e:
                log(f"[W{i}] 异常: {e}", "ERR")
                return None

    tasks = [worker(i) for i in range(1, args.count + 1)]
    results = await asyncio.gather(*tasks)

    ok = sum(1 for r in results if r and r.get("email"))
    log(f"批量完成: 成功 {ok}/{args.count}，结果见 accounts_gmail.txt", "OK")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Gmail 混合注册(浏览器铸BotGuard+HTTP手机验证)")
    ap.add_argument("--auto-sms", action="store_true", help="自动接码完成手机验证")
    ap.add_argument("--manual", action="store_true", help="浏览器里全手动填，脚本只接管手机步")
    ap.add_argument("--wait", type=int, default=240, help="等待到手机页的最大秒数")
    ap.add_argument("--count", type=int, default=1, help="批量注册个数")
    ap.add_argument("--parallel", type=int, default=1, help="并发窗口数(默认1)")
    ap.add_argument("--delete-window", action="store_true", help="注册后删除窗口(默认保留)")
    args = ap.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
