# -*- coding: utf-8 -*-
"""🔴 用 CDP 调试器提取 PerimeterX 自定义 base64 字母表。
setXHRBreakpoint("collector") 在 collector XHR 发送时暂停 → 遍历调用栈各帧 scopeChain →
Runtime.getProperties 扫出"长度60-70、独特字符多"的字符串(字母表通常是闭包常量，仍在栈上scope里)。
用法：python _px_debugger_alphabet.py "<proxy>"
"""
import asyncio, json, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from playwright.async_api import async_playwright
from common.browser_provider import get_browser_provider

SIGNUP = "https://signup.live.com/signup?lic=1"


def _looks_alphabet(s):
    return isinstance(s, str) and 58 <= len(s) <= 70 and len(set(s)) >= 50


async def _scan_paused(cdp, params, found):
    for frame in params.get("callFrames", [])[:12]:
        for scope in frame.get("scopeChain", []):
            obj = scope.get("object", {})
            oid = obj.get("objectId")
            if not oid:
                continue
            try:
                props = await cdp.send("Runtime.getProperties",
                                       {"objectId": oid, "ownProperties": True, "generatePreview": False})
            except Exception:
                continue
            for p in (props.get("result", []) + props.get("internalProperties", [])):
                v = p.get("value", {}) or {}
                if v.get("type") == "string" and _looks_alphabet(v.get("value", "")):
                    found[v["value"]] = found.get(v["value"], 0) + 1


async def _run(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_dbg", proxy_str=proxy)
    info = bb.open_browser(pid)
    found, paused_params, ev = {}, [], asyncio.Event()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()
        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Debugger.enable")
        await cdp.send("DOMDebugger.setXHRBreakpoint", {"url": "collector"})

        def on_paused(params):
            paused_params.append(params)
            ev.set()
        cdp.on("Debugger.paused", on_paused)

        try:
            await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass  # 可能因断点暂停导致 goto 超时，无妨

        # 最多等 3 次暂停（多个 collector XHR）
        for _ in range(3):
            try:
                await asyncio.wait_for(ev.wait(), timeout=40)
            except asyncio.TimeoutError:
                break
            ev.clear()
            cur = paused_params[-1]
            print(f"[dbg] 暂停 reason={cur.get('reason')} frames={len(cur.get('callFrames',[]))}")
            await _scan_paused(cdp, cur, found)
            if found:
                break
            try:
                await cdp.send("Debugger.resume")
            except Exception:
                break
        try:
            await cdp.send("Debugger.resume")
        except Exception:
            pass
    bb.close_browser(pid); bb.delete_browser(pid)

    print(f"[dbg] 候选字母表 {len(found)} 个:")
    for s, n in sorted(found.items(), key=lambda x: -len(set(x[0]))):
        print(f"  uniq={len(set(s))} len={len(s)}: {s}")
    json.dump(found, open("_px_alpha.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
