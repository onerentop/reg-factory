# -*- coding: utf-8 -*-
"""验证 CDP 自动化泄漏是否被堵上（rebrowser-playwright 是否真生效）。

在你真实的 ixBrowser + connect_over_cdp 同款会话里，加载 rebrowser 官方检测页
`bot-detector.rebrowser.net`，触发几次 page.evaluate 让泄漏测试有东西可抓，然后截图 +
dump 结果。**换 rebrowser 前后各跑一次对比**：

  关键看这几项（应为 not detected / 绿）：
    - dummyFn / exposeFunctionLeak / sourceUrlLeak  —— Runtime.enable 相关泄漏
    - mainWorldExecution                            —— 是否在 main world 执行（rebrowser 用 binding 规避）
    - navigatorWebdriver                            —— ixBrowser 应已处理

用法：
    python _verify_cdp_leak.py "<proxy_str>"     # 带代理，最贴近真实环境
    python _verify_cdp_leak.py                   # 不带代理也能测（CDP 泄漏与 IP 无关）

对照实验（PowerShell）：
    $env:REBROWSER_PATCHES_RUNTIME_FIX_MODE="0"; python _verify_cdp_leak.py   # 关修复 → 应见泄漏
    $env:REBROWSER_PATCHES_RUNTIME_FIX_MODE="addBinding"; python _verify_cdp_leak.py  # 开 → 应变绿
"""
import asyncio, sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: 触发 .env
from common.stealth_playwright import async_playwright, stealth_banner
from common.browser_provider import get_browser_provider

DETECTOR_URL = "https://bot-detector.rebrowser.net/"
SHOT = "_cdp_leak_check.png"


async def _main():
    proxy_str = sys.argv[1] if len(sys.argv) > 1 else ""
    print(stealth_banner())
    print(f"[verify] 检测页: {DETECTOR_URL}  代理: {'有' if proxy_str else '无'}")

    bb = get_browser_provider()
    profile_id = bb.create_browser(name="verify_cdp", proxy_str=proxy_str)
    info = bb.open_browser(profile_id)
    ws = info.get("ws", "")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            await page.goto(DETECTOR_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # 触发几次 main-world evaluate，让 dummyFn/mainWorldExecution 等测试有机会捕获泄漏
            for expr in ("1+1", "document.title", "document.querySelectorAll('*').length"):
                try:
                    await page.evaluate(expr)
                except Exception as e:
                    print(f"[verify] evaluate({expr!r}) 异常: {e}")
            await asyncio.sleep(4)

            try:
                await page.screenshot(path=SHOT, full_page=True)
                print(f"[verify] 截图已存: {SHOT}（绿=干净，红=仍泄漏）")
            except Exception as e:
                print(f"[verify] 截图失败: {e}")

            try:
                text = await page.evaluate("document.body.innerText")
                print("\n[verify] ===== 检测页结果文本 =====")
                print(text[:2000])
                print("[verify] ===========================")
            except Exception as e:
                print(f"[verify] 读取结果文本失败: {e}")

            # ---- 指纹×IP 对齐自检：出口 IP 国家 vs 浏览器时区/语言 ----
            try:
                geo_page = await context.new_page()
                await geo_page.goto("http://ip-api.com/json/", wait_until="domcontentloaded", timeout=30000)
                import json as _json
                geo_txt = await geo_page.evaluate("document.body.innerText")
                geo = _json.loads(geo_txt)
                locale = await geo_page.evaluate(
                    "({lang: navigator.language, langs: (navigator.languages||[]).join(','),"
                    " tz: Intl.DateTimeFormat().resolvedOptions().timeZone})"
                )
                print("\n[verify] ===== 指纹×IP 对齐自检 =====")
                print(f"  出口 IP        : {geo.get('query')}  国家={geo.get('countryCode')} ({geo.get('country')})")
                print(f"  IP 真实时区    : {geo.get('timezone')}")
                print(f"  浏览器时区     : {locale.get('tz')}")
                print(f"  navigator.lang : {locale.get('lang')}  languages=[{locale.get('langs')}]")
                tz_ok = geo.get("timezone") and geo.get("timezone") == locale.get("tz")
                cc = (geo.get("countryCode") or "").lower()
                lang = (locale.get("lang") or "").lower()
                lang_ok = cc and (cc in lang or lang.split("-")[-1] == cc)
                print(f"  >> 时区匹配: {'✅' if tz_ok else '❌ 不一致——PX 会扣分'}"
                      f"  | 语言匹配: {'✅' if lang_ok else '❌ 与出口国不符'}")
                print("[verify] 若出现 ❌：在 ixBrowser 档案里把时区/语言设为「跟随 IP」，或改 provider 的 _build_fingerprint")
                print("[verify] ===========================")
                await geo_page.close()
            except Exception as e:
                print(f"[verify] 指纹×IP 自检失败（不影响 CDP 结论）: {e}")
    finally:
        try:
            bb.close_browser(profile_id); bb.delete_browser(profile_id)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(_main())
