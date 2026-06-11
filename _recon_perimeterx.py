# -*- coding: utf-8 -*-
"""🔴 Phase 0 实弹侦查：起浏览器到 signup.live.com，录 PX 全链路 → 落语料库。
用法（机器自动跑，多半 FAIL）：python _recon_perimeterx.py bot "<proxy>"
用法（真人手动长按，求 PASS 黄金）：python _recon_perimeterx.py human "<proxy>"
"""
import asyncio, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from common.stealth_playwright import async_playwright
from common.browser_provider import get_browser_provider
from perimeterx_solver.corpus import SampleCorpus
from perimeterx_solver.recon.traffic_recorder import PxTrafficRecorder
from perimeterx_solver.recon.script_dumper import PxScriptDumper
from perimeterx_solver.recon.cookie_snapshotter import PxCookieSnapshotter
from perimeterx_solver.classify import is_px_url, classify_px_url, PxKind

SIGNUP = "https://signup.live.com/signup?lic=1"


async def _run(mode, proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name=f"px_recon_{mode}", proxy_str=proxy)
    info = bb.open_browser(pid)
    rec, dumper, snap = PxTrafficRecorder(), PxScriptDumper(), PxCookieSnapshotter()
    snaps, scripts = [], []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        pointer = []
        if mode == "human":
            # 录真人指针事件流（Phase 2 重放命脉）；init script 须在导航前注入
            await ctx.add_init_script(
                "window.__pxptr=[];['pointerdown','pointermove','pointerup'].forEach(function(t){"
                "document.addEventListener(t,function(e){window.__pxptr.push("
                "{x:e.clientX,y:e.clientY,t:e.timeStamp,type:t});},true);});")
        page = await ctx.new_page()

        async def on_response(resp):
            try:
                url = resp.url
                if not is_px_url(url):
                    return
                req = resp.request
                body = ""
                try:
                    body = req.post_data or ""
                except Exception:
                    pass
                rtext = ""
                try:
                    rtext = await resp.text()
                except Exception:
                    pass
                rec.on_request_finished(url, req.method, body, resp.status, rtext, req.headers, time.time())
                if classify_px_url(url, req.method) == PxKind.SCRIPT and rtext:
                    scripts.append(dumper.dump(url, rtext))
            except Exception:
                pass
        page.on("response", on_response)

        await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        snaps.append(snap.snapshot("on_load", time.time(), await ctx.cookies()))
        confirmed = "fail"
        if mode == "human":
            print(">>> 真人手动：完整填表并长按过码，过了再回车 <<<")
            await asyncio.get_event_loop().run_in_executor(None, input)
            try:
                pointer = await page.evaluate("window.__pxptr || []")
            except Exception:
                pointer = []
            # _px3 仅加载就常驻，不能据此判过；让真人显式确认（黄金样本命脉）
            ans = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("过码成功了吗? y=成功(黄金) / 其它=失败: "))
            confirmed = "pass" if ans.strip().lower() == "y" else "fail"
        else:
            await asyncio.sleep(60)  # bot：等挑战出现/失败（不长按，记为 fail）
        snaps.append(snap.snapshot("after_attempt", time.time(), await ctx.cookies()))

    bb.close_browser(pid); bb.delete_browser(pid)
    corpus = SampleCorpus()
    from perimeterx_solver.models import Sample
    s = Sample(run_id=f"{mode}_{int(time.time())}", outcome=confirmed,
               meta={"mode": mode, "proxy": proxy})
    s.requests = rec.captured
    s.cookie_snapshots = snaps
    s.script_refs = scripts
    s.pointer_stream = pointer
    corpus.save(s)
    print(f"[recon] outcome={s.outcome} run_id={s.run_id} reqs={len(rec.captured)} scripts={len(scripts)}")
    print(f"[recon] collector payloads={len(rec.collector_payloads())}")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else "bot",
                     sys.argv[2] if len(sys.argv) > 2 else ""))
