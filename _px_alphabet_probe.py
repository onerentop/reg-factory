# -*- coding: utf-8 -*-
"""🔴 运行时提取 PerimeterX 自定义 base64 字母表。
注入探针包住 String.prototype.{charAt,indexOf,split,slice} + Array 索引，
记录任何"长度55-70、独特字符多"的字符串（字母表特征）。
用法：python _px_alphabet_probe.py "<proxy>"   (PX_INSTR_WAIT 默认 30)
"""
import asyncio, json, os, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from playwright.async_api import async_playwright
from common.browser_provider import get_browser_provider

SIGNUP = "https://signup.live.com/signup?lic=1"

# 探针：包住几个 String 方法，凡 this 是长度 55-70、独特字符≥55 的串就记录（去重）
PROBE_JS = r"""
window.__pxalpha = window.__pxalpha || {};
(function(){
  function rec(s){
    try{
      if(typeof s==='string' && s.length>=48 && s.length<=80){
        var u={}; for(var i=0;i<s.length;i++)u[s[i]]=1;
        if(Object.keys(u).length>=44){ window.__pxalpha[s]=(window.__pxalpha[s]||0)+1; }
      }
    }catch(e){}
  }
  // 注：实测字母表经 bracket 取值 alphabet[i]（不可 hook）访问，下列 String 方法探针未能命中；
  // Array.join/fromCharCode 全局覆盖危险且只捕获到数据字节块。字母表提取需反混淆 main.min.js
  // 的 base64 例程或调试器在编码函数下断点（深 VM 逆向，见 crypto-spec 攻击向量）。
  ['charAt','indexOf','charCodeAt','split','slice','substring','lastIndexOf'].forEach(function(m){
    var orig=String.prototype[m];
    if(!orig) return;
    String.prototype[m]=function(){ rec(this); return orig.apply(this, arguments); };
    try{ String.prototype[m].toString=function(){return 'function '+m+'() { [native code] }';}; }catch(e){}
  });
})();
"""


async def _run(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_alpha", proxy_str=proxy)
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
                a = await fr.evaluate("window.__pxalpha || {}")
                for k, v in (a or {}).items():
                    found[k] = found.get(k, 0) + v
            except Exception:
                pass
    bb.close_browser(pid); bb.delete_browser(pid)

    print(f"[alpha] 候选字母表 {len(found)} 个:")
    for s, n in sorted(found.items(), key=lambda x: -x[1]):
        print(f"  hits={n} len={len(s)} uniq={len(set(s))}: {s}")
    json.dump(found, open("_px_alpha.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
