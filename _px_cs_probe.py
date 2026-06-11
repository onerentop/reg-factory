# -*- coding: utf-8 -*-
"""🔴 逆 cs(会话签名,64hex SHA256)：hook crypto.subtle.digest/sign，记录 输入→输出；
抓 egress body 里的 cs 字段，关联出 输出==cs 的那次，其输入即 cs 公式。
用法：python _px_cs_probe.py "<proxy>"   (PX_INSTR_WAIT 默认 35)
"""
import asyncio, json, os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from playwright.async_api import async_playwright   # 原版(hook 需主世界)
from common.browser_provider import get_browser_provider

SIGNUP = "https://signup.live.com/signup?lic=1"

PROBE_JS = r"""
window.__pxd = window.__pxd || [];
window.__pxe = window.__pxe || [];
(function(){
  function abhex(buf){
    try{ var v=new Uint8Array(buf.buffer||buf); var s=''; for(var i=0;i<v.length;i++)s+=('0'+v[i].toString(16)).slice(-2); return s; }catch(e){return '';}
  }
  function abtext(buf){
    try{ return new TextDecoder().decode(buf.buffer?buf:new Uint8Array(buf)); }catch(e){return '';}
  }
  function rec(kind, algo, input){
    var hx=abhex(input), tx=abtext(input);
    return {kind:kind, algo:''+algo, in_hex:hx.slice(0,400), in_text:(/^[\x09\x0a\x0d\x20-\x7e]*$/.test(tx)?tx.slice(0,300):''), in_len:hx.length/2};
  }
  if (window.crypto && crypto.subtle){
    var od=crypto.subtle.digest;
    crypto.subtle.digest=function(algo,data){
      var r=rec('digest',algo,data);
      var p=od.apply(crypto.subtle,arguments);
      try{ p.then(function(out){ r.out=abhex(out); window.__pxd.push(r); }); }catch(e){ window.__pxd.push(r); }
      return p;
    };
    if (crypto.subtle.sign){
      var os_=crypto.subtle.sign;
      crypto.subtle.sign=function(algo,key,data){
        var r=rec('sign',algo,data);
        var p=os_.apply(crypto.subtle,arguments);
        try{ p.then(function(out){ r.out=abhex(out); window.__pxd.push(r); }); }catch(e){ window.__pxd.push(r); }
        return p;
      };
    }
  }
  // 抓 egress body(取 cs 字段)
  var _send=XMLHttpRequest.prototype.send, _open=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){this.__u=u;return _open.apply(this,arguments);};
  XMLHttpRequest.prototype.send=function(b){ try{ if(this.__u&&(''+this.__u).indexOf('collector')>=0) window.__pxe.push(''+b); }catch(e){} return _send.apply(this,arguments); };
})();
"""


async def _run(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_cs", proxy_str=proxy)
    info = bb.open_browser(pid)
    digests, egress = [], []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        await ctx.add_init_script(PROBE_JS)
        page = await ctx.new_page()
        await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(int(os.environ.get("PX_INSTR_WAIT", "35")))
        for fr in page.frames:
            try:
                digests += (await fr.evaluate("window.__pxd || []")) or []
                egress += (await fr.evaluate("window.__pxe || []")) or []
            except Exception:
                pass
    bb.close_browser(pid); bb.delete_browser(pid)

    # 取 egress body 里的 cs
    import re
    css = set()
    for b in egress:
        m = re.search(r"(?:^|&)cs=([0-9a-f]{64})", b)
        if m:
            css.add(m.group(1))
    print(f"[cs] digest/sign 调用={len(digests)}  egress collector={len(egress)}  cs集={list(css)}")
    json.dump({"digests": digests, "css": list(css)}, open("_px_cs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # 关联：找 out==cs 的 digest
    hit = [d for d in digests if d.get("out") in css]
    if hit:
        for d in hit:
            print(f"\n[cs] ★命中★ algo={d['algo']} out={d['out'][:24]}..")
            print(f"     输入文本: {d.get('in_text','')!r}")
            print(f"     输入hex[:120]: {d.get('in_hex','')[:120]}  in_len={d.get('in_len')}")
    else:
        print("[cs] 未直接命中。所有 digest 输出前若干：")
        for d in digests[:12]:
            print(f"  algo={d['algo']} out={str(d.get('out'))[:20]} in_text={d.get('in_text','')[:80]!r} in_len={d.get('in_len')}")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
