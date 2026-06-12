# -*- coding: utf-8 -*-
"""🔴 录原始真人指针轨迹（注入 hsprotect OOPIF iframe，rebrowser 隐身保证真人能过码）。
长按按钮在 OOPIF iframe 内、事件不冒泡到主页面 → 必须把监听器注入该 iframe 帧。
你长按过码，捕获 pointerdown→move*→up 高精度轨迹（ML所需真人微动力学）+ collector长按payload+响应。
用法：python _px_traj_capture.py "<proxy>"
"""
import asyncio, json, os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("OUTLOOK_HUMAN_PRESS", "1")
os.environ.setdefault("OUTLOOK_HUMAN_WAIT_ROUNDS", "90")
import config  # noqa
# 原版 playwright：rebrowser 隔离世界会让 iframe 内监听器收不到指针(黄金 pointer=0 真因)。
# 捕获优先用原版(监听器在主世界生效)；代价是无隐身→必须配全新干净 IP+真人手动过码。
from playwright.async_api import async_playwright
from common.browser_provider import get_browser_provider
from register_outlook_standalone import register_outlook
from perimeterx_solver.classify import is_px_url, classify_px_url, PxKind, parse_collector_body
from perimeterx_solver.analysis.decryptor import Px2Decryptor

INJECT = r"""(function(){
  if (window.__trajOn) return 'already';
  window.__trajOn = true; window.__traj = [];
  ['pointerdown','pointermove','pointerup','pointercancel'].forEach(function(t){
    document.addEventListener(t,function(e){
      try{ window.__traj.push({type:t,x:e.clientX,y:e.clientY,px:e.pressure,
        mx:e.movementX,my:e.movementY,t:e.timeStamp,
        cx:e.coalescedEvents?e.getCoalescedEvents().length:0}); }catch(err){}
    },true);
  });
  return 'injected';
})()"""


async def _inject_loop(page, stop):
    """轮询把监听器注入所有 hsprotect 帧（含 OOPIF iframe）。"""
    while not stop.is_set():
        for fr in page.frames:
            try:
                if "hsprotect" in (fr.url or ""):
                    await fr.evaluate(INJECT)
            except Exception:
                pass
        await asyncio.sleep(1.0)


async def _run(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_traj", proxy_str=proxy)
    info = bb.open_browser(pid)
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()

        async def on_resp(resp):
            try:
                if not is_px_url(resp.url):
                    return
                req = resp.request
                if classify_px_url(resp.url, req.method) == PxKind.COLLECTOR:
                    try:
                        rt = await resp.text()
                    except Exception:
                        rt = ""
                    rows.append((req.post_data or "", rt))
            except Exception:
                pass
        page.on("response", on_resp)

        stop = asyncio.Event()
        injector = asyncio.create_task(_inject_loop(page, stop))
        print(">>> 脚本填表中…挑战出现后请手动长按过码（录你的原始轨迹）<<<")
        try:
            result = await register_outlook(page, ctx, 0)
        except Exception:
            result = None
        # 读所有 hsprotect 帧的轨迹
        traj = []
        for fr in page.frames:
            try:
                if "hsprotect" in (fr.url or ""):
                    traj += (await fr.evaluate("window.__traj || []")) or []
            except Exception:
                pass
        stop.set()
        try:
            await injector
        except Exception:
            pass
    bb.close_browser(pid); bb.delete_browser(pid)

    traj.sort(key=lambda e: e.get("t", 0))
    dec = Px2Decryptor()
    holds = []
    for body, rt in rows:
        cp = parse_collector_body(body)
        if cp.encrypted_blob and b"#px-captcha" in dec.decrypt(cp.encrypted_blob):
            do, ob = None, ""
            try:
                j = json.loads(rt); do = j.get("do")
                if j.get("ob"):
                    ob = dec.decrypt(j["ob"]).decode("latin1")
            except Exception:
                pass
            holds.append({"seq": cp.plaintext_fields.get("seq"),
                          "fields": cp.plaintext_fields,
                          "pt": dec.decrypt(cp.encrypted_blob).decode("latin1"), "do": do, "ob": ob})
    out = {"outcome": "pass" if (result and result[0]) else "fail",
           "email": result[0] if result and result[0] else None,
           "trajectory": traj, "holds": holds}
    json.dump(out, open("_px_trajectory.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    pdn = [e for e in traj if e["type"] == "pointerdown"]
    pmv = [e for e in traj if e["type"] == "pointermove"]
    pup = [e for e in traj if e["type"] == "pointerup"]
    print(f"\n[traj] outcome={out['outcome']} email={out['email']}")
    print(f"[traj] 原始轨迹: down={len(pdn)} move={len(pmv)} up={len(pup)}  collector长按={len(holds)}")
    if pdn and pup:
        print(f"[traj] down@({pdn[0]['x']},{pdn[0]['y']}) → 跨度 {(pup[-1]['t']-pdn[0]['t']):.0f}ms, {len(pmv)} move")
    print("[traj] 已存 _px_trajectory.json")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
