# -*- coding: utf-8 -*-
"""
gmail_botguard_probe.py — 混合方案关键实验：从真浏览器抓取 BotGuard `<` token。

做什么：
  1. ixBrowser + Playwright(CDP) 打开 Android 注册流（与 HTTP 脚本同一 flow）
  2. 自动填姓名/生日；失败可手动走（窗口里手填）
  3. 拦截 eOY7Bb(生日) 请求，提取：
       - `<` 开头 BotGuard token
       - reCAPTCHA token
       - 整套会话(cookies / f.sid / at / dsh / TL / bl / final_url)
  4. 全部存到 gmail_botguard_capture.json

用途：拿到真 token 后，再用 register_gmail_protocol 在“另一个 HTTP 会话”里
注入该 token，验证 BotGuard token 是否“跨会话可移植”（混合方案成败分水岭）。

运行：
  python gmail_botguard_probe.py
  python gmail_botguard_probe.py --manual   # 纯手动，只负责拦截
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: F401  (loads .env)
from common.browser_provider import get_browser_provider

try:
    from outlook_reg_loop import rotate_proxy_sid
except Exception:
    def rotate_proxy_sid(p):
        return p

IMSI = "460009188843340"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gmail_botguard_capture.json")

CONTINUE_RAW = (
    "https://accounts.google.com/o/android/auth?lang=zh&cc=CN"
    "&langCountry=zh_CN&xoauth_display_name=Android+Device"
    "&tmpl=new_account&source=android&return_user_id=true"
)


def build_signup_url(dsh=""):
    return (
        "https://accounts.google.com/lifecycle/flows/signup"
        "?biz=false&canSk=1&cc=cn"
        "&continue=" + urllib.parse.quote(CONTINUE_RAW, safe="")
        + "&dsh=" + urllib.parse.quote(dsh, safe="")
        + "&flowName=GlifSetupAndroid"
        + "&hl=zh-Hans-CN"
        + f"&imsi={IMSI}"
        + "&multilogin=1"
        + "&source=com.google.android.gm"
        + "&use_native_navigation=0"
    )


def parse_eoy7bb(post_data):
    """从 eOY7Bb 的 postData(urlencoded) 解出 f.req，再抽 BotGuard / reCAPTCHA token。"""
    decoded = urllib.parse.unquote_plus(post_data)
    if "f.req=" not in decoded:
        return None
    freq = decoded.split("f.req=", 1)[1].split("&at=", 1)[0]
    at = ""
    if "&at=" in decoded:
        at = decoded.split("&at=", 1)[1].split("&", 1)[0]
    botguard = None
    recaptcha = None
    try:
        outer = json.loads(freq)              # [[["eOY7Bb","<inner json str>",null,"generic"]]]
        inner = json.loads(outer[0][0][1])    # 真正的生日 payload
        # 结构: [[Y,M,D],1,...,[ "<botguard>", null*4, ["<recaptcha>", ...] ] ]
        def walk(x):
            nonlocal botguard, recaptcha
            if isinstance(x, str):
                if x.startswith("<") and len(x) > 500 and botguard is None:
                    botguard = x
                elif x.startswith("0cAFce") or x.startswith("0cAFcW"):
                    if recaptcha is None:
                        recaptcha = x
            elif isinstance(x, list):
                for e in x:
                    walk(e)
        walk(inner)
    except Exception as e:
        print(f"  [parse] inner parse failed: {e}")
    return {"f_req": freq, "at": at, "botguard": botguard, "recaptcha": recaptcha}


async def auto_fill(page):
    """尽力自动填姓名/生日；失败就交给人工。返回 True 表示已尝试推进。"""
    # 姓名页
    try:
        await page.wait_for_selector("input[name=firstName], input#firstName", timeout=15000)
        await page.fill("input[name=firstName], input#firstName", "Max")
        await page.fill("input[name=lastName], input#lastName", "Weber")
        await page.get_by_role("button", name=re.compile(r"下一步|Next", re.I)).first.click()
        print("  [auto] name submitted")
    except Exception as e:
        print(f"  [auto] name page skipped: {e}")
        return False
    # 生日页
    try:
        await page.wait_for_selector("input#day, input[name=day]", timeout=15000)
        # 月份：Material select
        try:
            await page.click("#month")
            await page.click("ul[aria-label] li:nth-child(5), [role=option]:nth-child(5)")
        except Exception:
            pass
        await page.fill("input#day, input[name=day]", "19")
        await page.fill("input#year, input[name=year]", "1991")
        try:
            await page.click("#gender")
            await page.click("[role=option]:nth-child(2)")
        except Exception:
            pass
        await page.get_by_role("button", name=re.compile(r"下一步|Next", re.I)).first.click()
        print("  [auto] birthday submitted")
        return True
    except Exception as e:
        print(f"  [auto] birthday page skipped: {e}")
        return False


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true", help="纯手动，只拦截")
    ap.add_argument("--wait", type=int, default=300, help="最多等待秒数")
    args = ap.parse_args()

    proxy_base = (os.environ.get("OUTLOOK_PROXIES", "") or "").splitlines()
    proxy = rotate_proxy_sid(proxy_base[0]) if proxy_base else None
    print(f"proxy: {(proxy or 'DIRECT')[:55]}")

    bb = get_browser_provider()
    pid = None
    captured = {}

    try:
        pid = bb.create_browser(name="gmail_bg_probe", proxy_str=proxy)
        info = bb.open_browser(pid)
        ws = info.get("ws", "")
        print(f"cdp ws: {ws[:60]}")

        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            client = await ctx.new_cdp_session(page)
            await client.send("Network.enable")

            done = asyncio.Event()

            def on_request(params):
                req = params.get("request", {})
                url = req.get("url", "")
                if "batchexecute" in url and "eOY7Bb" in urllib.parse.unquote(url):
                    post = req.get("postData", "")
                    if post:
                        info2 = parse_eoy7bb(post)
                        if info2 and info2.get("botguard"):
                            captured.update(info2)
                            bg = info2["botguard"]
                            rc = info2.get("recaptcha")
                            print(f"\n  >>> CAPTURED eOY7Bb")
                            print(f"      BotGuard token: {len(bg)} chars  head={bg[:40]}")
                            print(f"      reCAPTCHA token: {len(rc) if rc else 0} chars")
                            done.set()

            client.on("Network.requestWillBeSent", on_request)

            signup_url = build_signup_url()
            print(f"goto: {signup_url[:80]}...")
            await page.goto(signup_url, wait_until="domcontentloaded", timeout=60000)
            print(f"landed: {page.url[:80]}")

            if not args.manual:
                await auto_fill(page)

            print("\n" + "=" * 56)
            print("若自动填充未完成：请在弹出的窗口里手动走 姓名→生日 并点下一步")
            print(f"脚本会自动拦截 eOY7Bb 请求并存盘。最多等 {args.wait}s")
            print("=" * 56 + "\n")

            try:
                await asyncio.wait_for(done.wait(), timeout=args.wait)
            except asyncio.TimeoutError:
                print("  [timeout] 未捕获到 eOY7Bb")

            # 抓会话信息
            try:
                cookies = await ctx.cookies()
                captured["cookies"] = {c["name"]: c["value"] for c in cookies
                                       if "google" in c.get("domain", "")}
                captured["final_url"] = page.url
                # 从页面抓 f.sid / at / bl
                js = """() => {
                    const g = window.WIZ_global_data || {};
                    return {fsid: g.FdrFJe, at: g.SNlM0e, bl: g.cfb2h};
                }"""
                meta = await page.evaluate(js)
                captured.update({k: v for k, v in (meta or {}).items() if v})
            except Exception as e:
                print(f"  [session] grab failed: {e}")

        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(captured, f, indent=2, ensure_ascii=False)
        print(f"\n保存 -> {OUT}")
        print(f"  botguard: {'YES ' + str(len(captured.get('botguard',''))) + ' chars' if captured.get('botguard') else 'NO'}")
        print(f"  recaptcha: {'YES' if captured.get('recaptcha') else 'NO'}")
        print(f"  cookies: {len(captured.get('cookies', {}))}")
        print(f"  fsid={captured.get('fsid')} bl={captured.get('bl')}")

    finally:
        if pid:
            try:
                bb.close_browser(pid)
                await asyncio.sleep(1)
                bb.delete_browser(pid)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
