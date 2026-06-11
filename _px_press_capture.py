# -*- coding: utf-8 -*-
"""🔴 抓机器自动长按的 collector 长按POST(请求+响应) → 供 真人PASS vs 机器FAIL 差分。
用法：python _px_press_capture.py "<proxy>"
"""
import asyncio, json, os, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("OUTLOOK_REG_MAX_PRESS", "5")
os.environ.setdefault("OUTLOOK_PRESS_HARD_CAP", "1")
import config  # noqa
from common.stealth_playwright import async_playwright
from common.browser_provider import get_browser_provider
from register_outlook_standalone import register_outlook
from perimeterx_solver.classify import is_px_url, classify_px_url, PxKind, parse_collector_body
from perimeterx_solver.analysis.decryptor import Px2Decryptor


async def _run(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_presscap", proxy_str=proxy)
    info = bb.open_browser(pid)
    rows = []  # (body, resp_text)
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

        try:
            await register_outlook(page, ctx, 0)   # 自动长按 ~5 次后放弃
        except Exception:
            pass
    bb.close_browser(pid); bb.delete_browser(pid)

    dec = Px2Decryptor()
    out = []
    for body, rt in rows:
        cp = parse_collector_body(body)
        if not cp.encrypted_blob:
            continue
        pt = dec.decrypt(cp.encrypted_blob)
        if b"#px-captcha" not in pt:
            continue
        do, ob = "?", ""
        try:
            j = json.loads(rt); do = j.get("do")
            if j.get("ob"):
                ob = dec.decrypt(j["ob"]).decode("latin1")
        except Exception:
            pass
        out.append({"seq": cp.plaintext_fields.get("seq"), "pt": pt.decode("latin1"),
                    "fields": cp.plaintext_fields, "do": do, "ob": ob})
    json.dump(out, open("_px_fail_press.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[presscap] 抓到机器长按POST {len(out)} 个 → _px_fail_press.json")
    for o in out:
        print(f"  seq={o['seq']} do={o['do']} ob={o['ob'][:70]!r} pt_len={len(o['pt'])}")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
