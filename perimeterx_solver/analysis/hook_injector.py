from enum import Enum


class HookFamily(str, Enum):
    NETWORK_EGRESS = "network_egress"
    ENCODING = "encoding"
    BEHAVIORAL = "behavioral"
    FINGERPRINT = "fingerprint"


# toString 伪装：把包装函数的 toString 改成原生码形态，防 VM 检测 hook
_TOSTRING_GUARD = """
function __pxNative(fn, name){
  try{ fn.toString = function(){ return "function " + name + "() { [native code] }"; }; }catch(e){}
  return fn;
}
"""

_SNIPPETS = {
    HookFamily.NETWORK_EGRESS: """
(function(){
  var _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = __pxNative(function(body){
    try{ window.__pxhook("egress_xhr", {url: this.__pxurl||"", body: String(body)}); }catch(e){}
    return _send.apply(this, arguments);
  }, "send");
  var _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = __pxNative(function(m,u){ this.__pxurl=u; return _open.apply(this, arguments); }, "open");
  if (window.fetch){ var _f = window.fetch; window.fetch = __pxNative(function(u,o){
    try{ window.__pxhook("egress_fetch", {url:String(u), body:(o&&o.body)?String(o.body):""}); }catch(e){}
    return _f.apply(this, arguments); }, "fetch"); }
})();""",
    HookFamily.ENCODING: """
(function(){
  var _btoa = window.btoa;
  window.btoa = __pxNative(function(s){ try{ window.__pxhook("btoa", {len:(""+s).length, head:(""+s).slice(0,64)}); }catch(e){} return _btoa.apply(this, arguments); }, "btoa");
  var _str = JSON.stringify;
  JSON.stringify = __pxNative(function(o){ var r=_str.apply(this, arguments); try{ if(r && r.length>40) window.__pxhook("json", {head:r.slice(0,200), len:r.length}); }catch(e){} return r; }, "stringify");
})();""",
    HookFamily.BEHAVIORAL: """
(function(){
  var _raf = window.requestAnimationFrame;
  window.requestAnimationFrame = __pxNative(function(cb){ try{ window.__pxhook("raf", {t: (performance&&performance.now)?performance.now():0}); }catch(e){} return _raf.apply(this, arguments); }, "requestAnimationFrame");
  var _ael = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = __pxNative(function(type){ try{ if(type==="mousedown"||type==="pointermove"||type==="pointerdown") window.__pxhook("listener", {type:type}); }catch(e){} return _ael.apply(this, arguments); }, "addEventListener");
})();""",
    HookFamily.FINGERPRINT: """
(function(){
  try{
    var nav = navigator;
    window.__pxhook("fp_navigator", {ua: nav.userAgent, plat: nav.platform, hc: nav.hardwareConcurrency, dm: nav.deviceMemory, langs: (nav.languages||[]).join(",")});
  }catch(e){}
})();""",
}


class HookInjector:
    """生成行为锚点 hook JS（Strategy 四族）。捕获经 window.__pxhook(kind,data) 上报。"""

    def snippet(self, family: HookFamily) -> str:
        return _SNIPPETS[family]

    def build(self, families) -> str:
        parts = [_TOSTRING_GUARD] + [_SNIPPETS[f] for f in families]
        return "\n".join(parts)
