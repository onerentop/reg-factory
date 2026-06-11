# -*- coding: utf-8 -*-
"""🔴 真人黄金样本捕获：脚本用 rebrowser 隐身自动填表到挑战出现，你在窗口手动长按过码；
全程抓 collector 网络 + 录指针流 → 解密存黄金样本(供 Task15 差分)。
用法：python _golden_capture.py "<住宅代理>"   (或 "" 直连家里IP)
"""
import asyncio, json, os, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("OUTLOOK_HUMAN_PRESS", "1")
import config  # noqa
from common.stealth_playwright import async_playwright, stealth_banner
from common.browser_provider import get_browser_provider
from register_outlook_standalone import register_outlook
from perimeterx_solver.corpus import SampleCorpus
from perimeterx_solver.models import Sample, CapturedRequest
from perimeterx_solver.classify import is_px_url, classify_px_url, PxKind, parse_collector_body
from perimeterx_solver.analysis.decryptor import Px2Decryptor

POINTER_JS = ("window.__pxptr=[];['pointerdown','pointermove','pointerup'].forEach(function(t){"
              "document.addEventListener(t,function(e){window.__pxptr.push("
              "{x:e.clientX,y:e.clientY,t:e.timeStamp,type:t});},true);});")


async def _run(proxy):
    print(stealth_banner())
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_golden", proxy_str=proxy)
    info = bb.open_browser(pid)
    captured = []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        await ctx.add_init_script(POINTER_JS)
        page = await ctx.new_page()

        async def on_response(resp):
            try:
                if not is_px_url(resp.url):
                    return
                req = resp.request
                if classify_px_url(resp.url, req.method) != PxKind.COLLECTOR:
                    return
                body = ""
                try:
                    body = req.post_data or ""
                except Exception:
                    pass
                captured.append(CapturedRequest(url=resp.url, method=req.method, req_body=body,
                                                resp_status=resp.status, ts=time.time()))
            except Exception:
                pass
        page.on("response", on_response)

        print(">>> 脚本自动填表中…挑战出现后请在窗口里手动长按过码（最多等 ~4.5 分钟）<<<")
        result = await register_outlook(page, ctx, 0)
        try:
            pointer = await page.evaluate("window.__pxptr || []")
        except Exception:
            pointer = []
        final_url = page.url
    try:
        bb.close_browser(pid); bb.delete_browser(pid)
    except Exception:
        pass

    email = result[0] if result and result[0] else None
    outcome = "pass" if email else "fail"
    dec = Px2Decryptor()
    decoded = []
    for c in captured:
        cp = parse_collector_body(c.req_body)
        try:
            pt = dec.decrypt(cp.encrypted_blob)
            decoded.append({"len": len(pt), "head": pt[:160].decode("latin1")})
        except Exception as e:
            decoded.append({"err": str(e)})

    corpus = SampleCorpus()
    s = Sample(run_id=f"golden_{int(time.time())}", outcome=outcome,
               meta={"mode": "human_golden", "proxy": proxy, "email": email, "final_url": final_url})
    s.requests = captured
    s.pointer_stream = pointer
    corpus.save(s)
    json.dump(decoded, open("_px_golden_decoded.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\n[golden] outcome={outcome} email={email}")
    print(f"[golden] collector载荷={len(captured)} 指针事件={len(pointer)} final_url={final_url[:70]}")
    for i, d in enumerate(decoded):
        print(f"  载荷[{i}] {str(d)[:170]}")
    print(f"[golden] 样本已存 run_id={s.run_id}（_px_golden_decoded.json 有解密明文）")
    print("[golden] 若你确实过码了但 outcome=fail，无妨——collector 载荷已抓到，告诉我即可")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
