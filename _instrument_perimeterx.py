# -*- coding: utf-8 -*-
"""🔴 Phase 1 实弹插桩：在受控浏览器跑 PX collector，注入行为锚点 hook，捕获明文载荷 + 定位 crypto。
用法：python _instrument_perimeterx.py "<proxy>"
  默认等待 input() 回车（手动控时）；设 PX_INSTR_WAIT=30 则改为固定等待 30s（可自动跑）。

事件收集：hook 把事件 push 进页面 window.__pxevents 数组，结束前 page.evaluate 整体读出
（遍历所有 frame，collector 可能在 hsprotect iframe），避免 expose_binding 在关闭时投递崩溃。
插桩用**原版 playwright**（不要 rebrowser 隐身——其隔离世界会让 hook 不落主世界）。
"""
import asyncio, json, os, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from playwright.async_api import async_playwright
from common.browser_provider import get_browser_provider
from perimeterx_solver.analysis.hook_injector import HookInjector, HookFamily
from perimeterx_solver.analysis.instrumented_session import PxInstrumentedSession

SIGNUP = "https://signup.live.com/signup?lic=1"
# __pxhook 定义成数组收集器，须在 hook_js 之前注入
_COLLECTOR_JS = ("window.__pxevents=window.__pxevents||[];"
                 "window.__pxhook=function(k,d){window.__pxevents.push({kind:k,data:d,t:Date.now()});};")


async def _collect_events(page):
    """从主页 + 所有 frame 合并 window.__pxevents。"""
    out = []
    for fr in page.frames:
        try:
            evs = await fr.evaluate("window.__pxevents || []")
            if evs:
                out.extend(evs)
        except Exception:
            pass
    out.sort(key=lambda e: e.get("t", 0))
    return out


async def _run(proxy):
    inj = HookInjector()
    hook_js = inj.build([HookFamily.NETWORK_EGRESS, HookFamily.ENCODING,
                         HookFamily.BEHAVIORAL, HookFamily.FINGERPRINT])
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_instr", proxy_str=proxy)
    info = bb.open_browser(pid)
    events = []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        await ctx.add_init_script(_COLLECTOR_JS)
        await ctx.add_init_script(hook_js)
        page = await ctx.new_page()
        await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        wait_env = os.environ.get("PX_INSTR_WAIT", "").strip()
        if wait_env.isdigit():
            print(f">>> 固定等待 {wait_env}s 收集事件（collector 仅加载即自动发 POST） <<<")
            await asyncio.sleep(int(wait_env))
        else:
            print(">>> 让挑战出现（真人或自动皆可）；收集足够事件后回车 <<<")
            await asyncio.get_event_loop().run_in_executor(None, input)
        try:
            events = await _collect_events(page)
        except Exception as e:
            print(f"[instr] 收集事件异常: {e}")
    bb.close_browser(pid); bb.delete_browser(pid)

    with open("_px_events.json", "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    result = PxInstrumentedSession().analyze(events)
    from collections import Counter
    print(f"[instr] events={result.event_count}  类型={dict(Counter(e['kind'] for e in events))}")
    print(f"[instr] traced egress={getattr(result.traced,'egress_url',None)}")
    print(f"[instr] plaintext head={getattr(result.traced,'plaintext_head','')[:300]}")
    print(f"[instr] crypto kinds={result.crypto.kinds}")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
