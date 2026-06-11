# -*- coding: utf-8 -*-
"""🔴 直接抓明文：自定义 base64 编码器读输入必逐字符 charCodeAt，明文是长串(~400+字节)。
hook charCodeAt/charAt 记录长 this → 拿到编码前明文(绕开字母表)。
用法：python _px_plaintext_probe.py "<proxy>"  (PX_INSTR_WAIT 默认 30)
"""
import asyncio, json, os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from playwright.async_api import async_playwright
from common.browser_provider import get_browser_provider

SIGNUP = "https://signup.live.com/signup?lic=1"

# 记录被 charCodeAt/charAt 逐字符读取的长字符串(疑似编码器输入明文)。按 len+前缀去重。
PROBE_JS = r"""
window.__pxpt = window.__pxpt || {};
(function(){
  function rec(s){
    try{
      if(typeof s==='string' && s.length>=120 && s.length<=20000){
        var key = s.length + '|' + s.slice(0,24);
        if(!window.__pxpt[key]) window.__pxpt[key] = s;
      }
    }catch(e){}
  }
  ['charCodeAt','charAt','codePointAt'].forEach(function(m){
    var orig=String.prototype[m];
    if(!orig) return;
    String.prototype[m]=function(){ rec(this); return orig.apply(this, arguments); };
    try{ String.prototype[m].toString=function(){return 'function '+m+'() { [native code] }';}; }catch(e){}
  });
})();
"""


def _printable(s):
    return sum(1 for c in s if 32 <= ord(c) < 127) / max(1, len(s))


async def _run(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_pt", proxy_str=proxy)
    info = bb.open_browser(pid)
    found = {}
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        await ctx.add_init_script(PROBE_JS)
        page = await ctx.new_page()
        await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(int(os.environ.get("PX_INSTR_WAIT", "30")))
        for fr in page.frames:
            try:
                d = await fr.evaluate("window.__pxpt || {}")
                found.update(d or {})
            except Exception:
                pass
    bb.close_browser(pid); bb.delete_browser(pid)

    json.dump(found, open("_px_plaintext.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[pt] 长字符串 {len(found)} 个。按可打印率+长度挑可疑明文:")
    items = sorted(found.values(), key=lambda s: -len(s))
    for s in items[:15]:
        pr = _printable(s)
        tag = " <==疑明文" if (pr > 0.85 and any(ch in s for ch in '{}[]":,')) else ""
        print(f"  len={len(s)} printable={pr:.2f}{tag}: {s[:100]!r}")
