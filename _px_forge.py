# -*- coding: utf-8 -*-
"""🔴 Phase2 hybrid-mint 伪造实验：浏览器填表到挑战(拿 fresh session 的 cs/sid/...body字段)，
HTTP 提交伪造长按 payload(黄金行为+刷新时间戳) → 解响应验 _px3。绕开 cs 逆向。
用法：python _px_forge.py "<proxy>"   (浏览器与提交同代理/同出口IP)
"""
import asyncio, os, re, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("OUTLOOK_HUMAN_PRESS", "1")
os.environ.setdefault("OUTLOOK_HUMAN_WAIT_ROUNDS", "40")
import requests
import config  # noqa
from common.stealth_playwright import async_playwright
from common.browser_provider import get_browser_provider
from register_outlook_standalone import register_outlook
from perimeterx_solver.corpus import SampleCorpus
from perimeterx_solver.classify import parse_collector_body, classify_px_url, PxKind, is_px_url
from perimeterx_solver.analysis.decryptor import Px2Decryptor, Px2Encoder

URL = "https://collector-PXzC5j78di.hsprotect.net/api/v2/msft"


def _golden_presshold_blob():
    dec = Px2Decryptor()
    g = SampleCorpus().golden()
    for r in g.requests:
        cp = parse_collector_body(r.req_body)
        if cp.encrypted_blob and b"#px-captcha" in dec.decrypt(cp.encrypted_blob):
            return cp.encrypted_blob
    return None


def _forge_payload(golden_blob):
    """黄金长按 payload 刷新时间戳重编码。
    注：实测 do:[] 的根因不是时间戳(原样重编码也 do:[])，而是 payload 绑定黄金挑战的
    每挑战令牌(如 bff5b218，仅在长按 payload、不在指纹/body)→ 重放到新挑战令牌不匹配被拒。
    要全 HTTP 伪造需从新挑战 iframe 提取该令牌并替换。"""
    dec, enc = Px2Decryptor(), Px2Encoder()
    pt = dec.decrypt(golden_blob)
    now = int(time.time() * 1000)
    tss = sorted(set(re.findall(rb"17811\d{8}", pt)))
    if len(tss) >= 2:
        pt = pt.replace(tss[0], str(now - 2500).encode())
        pt = pt.replace(tss[-1], str(now).encode())
    return enc.encode(pt)


def _to_requests_proxy(proxy):
    if not proxy:
        return None
    if "@" in proxy:
        return {"http": proxy, "https": proxy}
    s, scheme = proxy, "socks5h"
    if "://" in s:
        sc, s = s.split("://", 1)
        scheme = "socks5h" if "socks" in sc else sc
    parts = s.split(":")
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        pw = ":".join(parts[3:])
        u = f"{scheme}://{user}:{pw}@{host}:{port}"
        return {"http": u, "https": u}
    return None


def _submit(body, proxy):
    H = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
         "Origin": "https://iframe.hsprotect.net", "Referer": "https://iframe.hsprotect.net/",
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36", "Accept": "*/*"}
    px = _to_requests_proxy(proxy)
    r = requests.post(URL, data=body.encode(), headers=H, proxies=px, timeout=25)
    ob = ""
    try:
        ob = Px2Decryptor().decrypt(r.json().get("ob", "")).decode("latin1")
    except Exception:
        pass
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text, ob


async def _run(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_forge", proxy_str=proxy)
    info = bb.open_browser(pid)
    bodies = []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()

        resps = []

        async def on_resp(resp):
            try:
                if not is_px_url(resp.url):
                    return
                req = resp.request
                if classify_px_url(resp.url, req.method) == PxKind.COLLECTOR:
                    b = req.post_data or ""
                    bodies.append(b)
                    try:
                        rt = await resp.text()
                    except Exception:
                        rt = ""
                    resps.append((b, rt))
            except Exception:
                pass
        page.on("response", on_resp)

        drive = asyncio.create_task(register_outlook(page, ctx, 0))
        # 等指纹序列发完(seq>=2)，用最高seq的body——真实长按在seq=3,在seq=2伪造会被结构性拒(do:[])
        fresh = None
        for _ in range(80):
            await asyncio.sleep(2)
            best = None
            for b in bodies:
                f = parse_collector_body(b).plaintext_fields
                if f.get("sid") and f.get("cs") and f.get("seq", "").isdigit():
                    if best is None or int(f["seq"]) > int(best[1]["seq"]):
                        best = (b, f)
            if best and int(best[1]["seq"]) >= 2:
                fresh = best
                break
        try:
            cookies = await ctx.cookies()
        except Exception:
            cookies = []

        import json as _json
        dec = Px2Decryptor()
        if fresh:
            body, f = fresh
            print(f"[forge] fresh session: seq={f.get('seq')} cs={f.get('cs','')[:16]}.. sid={f.get('sid','')[:20]}..")
            print(f"[forge] cookies: {[c['name'] for c in cookies if c['name'].startswith(('_px','px'))]}")
            for b, rt in resps[-4:]:
                sq = parse_collector_body(b).plaintext_fields.get("seq", "?")
                do, obd = "?", ""
                try:
                    j = _json.loads(rt); do = j.get("do")
                    if j.get("ob"):
                        obd = dec.decrypt(j["ob"]).decode("latin1")[:80]
                except Exception:
                    pass
                print(f"   seq={sq} do={do} ob={obd!r}")

            golden = _golden_presshold_blob()
            forged_payload = _forge_payload(golden)
            nf = dict(f); nf.pop("payload", None)
            try:
                nf["seq"] = str(int(f.get("seq", "0")) + 1)
                nf["rsc"] = str(int(f.get("rsc", "1")) + 1)
            except Exception:
                pass
            import random
            nf["pc"] = "".join(str(random.randint(0, 9)) for _ in range(16))  # 全新 pc(每请求唯一)
            forged_body = "&".join(["payload=" + forged_payload] + [f"{k}={v}" for k, v in nf.items()])
            print(f"[forge] 提交伪造长按(浏览器仍存活) body len={len(forged_body)} seq={nf['seq']}")
            loop = asyncio.get_event_loop()
            status, js, ob = await loop.run_in_executor(None, lambda: _submit(forged_body, proxy))
            print(f"[forge] status={status} resp={str(js)[:160]}")
            print(f"[forge] ob解密={ob[:300]}")
            print(f"[forge] >>> {'★ _px3 出现! 伪造成功 ★' if '_px3' in ob else '_pxde富化' if '_pxde' in ob else '看ob'}")

        drive.cancel()
        try:
            await drive
        except (asyncio.CancelledError, Exception):
            pass
    bb.close_browser(pid); bb.delete_browser(pid)
    if not fresh:
        print("[forge] 未拿到 fresh 挑战 session（挑战未激活）")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
