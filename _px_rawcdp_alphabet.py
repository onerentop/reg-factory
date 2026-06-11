# -*- coding: utf-8 -*-
"""🔴 原始 CDP（脱离 Playwright）提取 PerimeterX 自定义 base64 字母表 —— v2。
Target.setAutoAttach(flatten+waitForDebuggerOnStart) 覆盖 page+所有 OOPIF iframe，
每个 session 装 Debugger + DOMDebugger.setXHRBreakpoint("collector") + runIfWaitingForDebugger。
轮询式消息泵处理事件洪流；collector XHR 发送时暂停 → 遍历调用栈 scopeChain →
Runtime.getProperties 扫"长度 48-72、独特字符≥44"的字符串(字母表=闭包常量)。
用法：python _px_rawcdp_alphabet.py "<proxy>"
"""
import json, sys, time
import websocket  # websocket-client
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from common.browser_provider import get_browser_provider

SIGNUP = "https://signup.live.com/signup?lic=1"


def _looks(s):
    return isinstance(s, str) and 48 <= len(s) <= 72 and len(set(s)) >= 44


class CDP:
    def __init__(self, ws_url):
        # suppress_origin：Chrome CDP 用 --remote-allow-origins 拒绝带 Origin 头的连接(403)，去掉它
        self.ws = websocket.create_connection(ws_url, max_size=None, enable_multithread=True,
                                              suppress_origin=True)
        self.ws.settimeout(2)
        self._id = 0
        self.resp = {}        # id -> message
        self.event_q = []     # 持久事件队列(wait_resp 期间到达的事件不丢)
        self.sessions = set()

    def cmd(self, method, params=None, sid=None):
        self._id += 1
        m = {"id": self._id, "method": method, "params": params or {}}
        if sid:
            m["sessionId"] = sid
        self.ws.send(json.dumps(m))
        return self._id

    def pump(self):
        """drain 当前可读消息：响应入 self.resp，事件入 self.event_q（不丢）。"""
        while True:
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                break
            except Exception:
                break
            if "id" in msg:
                self.resp[msg["id"]] = msg
            else:
                self.event_q.append(msg)

    def drain_events(self):
        evs = self.event_q
        self.event_q = []
        return evs

    def wait_resp(self, mid, deadline):
        while time.time() < deadline:
            if mid in self.resp:
                return self.resp.pop(mid)
            self.pump()
        return None


def setup_session(cdp, sid):
    if sid in cdp.sessions:
        return
    cdp.sessions.add(sid)
    cdp.cmd("Debugger.enable", sid=sid)
    cdp.cmd("DOMDebugger.setXHRBreakpoint", {"url": "collector"}, sid=sid)
    # 递归 auto-attach：让本 session 的子 OOPIF iframe(如 hsprotect)也附着，否则其 XHR 抓不到
    cdp.cmd("Target.setAutoAttach",
            {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}, sid=sid)
    cdp.cmd("Runtime.runIfWaitingForDebugger", sid=sid)


_ARGS_EXPR = ("try{JSON.stringify(Array.prototype.slice.call(arguments).map(function(a){"
              "return (typeof a==='string')?('STR['+a.length+']:'+a.slice(0,400)):"
              "(a&&typeof a==='object'&&a.length!==undefined)?('ARR['+a.length+']:'+"
              "Array.prototype.slice.call(a,0,80).join(',')):typeof a;}))}catch(e){''+e}")


def scan_paused(cdp, sid, params, found, deadline, dump):
    """暂停态全量 dump：每帧函数名/位置 + scope 字符串变量 + 实参(evaluateOnCallFrame)。"""
    for fi, fr in enumerate(params.get("callFrames", [])[:20]):
        loc = fr.get("location", {})
        # 抓本帧实参（明文输入很可能是某帧实参：字符串或字节数组）
        args_val = ""
        cfid = fr.get("callFrameId")
        if cfid:
            mid = cdp.cmd("Debugger.evaluateOnCallFrame",
                          {"callFrameId": cfid, "expression": _ARGS_EXPR, "returnByValue": True}, sid=sid)
            r = cdp.wait_resp(mid, deadline)
            args_val = (r or {}).get("result", {}).get("result", {}).get("value", "")
        frame_rec = {
            "i": fi,
            "fn": fr.get("functionName", ""),
            "scriptId": loc.get("scriptId"),
            "line": loc.get("lineNumber"),
            "col": loc.get("columnNumber"),
            "args": args_val,
            "vars": {},
        }
        for sc in fr.get("scopeChain", []):
            oid = sc.get("object", {}).get("objectId")
            if not oid:
                continue
            mid = cdp.cmd("Runtime.getProperties", {"objectId": oid, "ownProperties": True}, sid=sid)
            r = cdp.wait_resp(mid, deadline)
            for prop in (r or {}).get("result", {}).get("result", []):
                v = prop.get("value", {}) or {}
                if v.get("type") == "string":
                    s = v.get("value", "")
                    if 4 <= len(s) <= 4000:
                        frame_rec["vars"][f"{sc.get('type')}:{prop.get('name')}"] = s
                        if _looks(s):
                            found[s] = found.get(s, 0) + 1
        dump.append(frame_rec)


def main(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_rawcdp", proxy_str=proxy)
    info = bb.open_browser(pid)
    ws_url = info.get("ws", "")
    print(f"[rawcdp] 连 {ws_url[:55]}...")
    found = {}
    cdp = CDP(ws_url)
    deadline = time.time() + 90
    try:
        cdp.cmd("Target.setAutoAttach",
                {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})
        ct = cdp.cmd("Target.createTarget", {"url": SIGNUP})
        r = cdp.wait_resp(ct, time.time() + 10)
        print(f"[rawcdp] createTarget -> {r.get('result') if r else 'NO RESP'}")
        n_pause = 0
        seen_methods = {}
        pause_dump = []
        while time.time() < deadline and not pause_dump:
            cdp.pump()
            for ev in cdp.drain_events():
                m = ev.get("method")
                seen_methods[m] = seen_methods.get(m, 0) + 1
                if m == "Target.attachedToTarget":
                    sid = ev["params"]["sessionId"]
                    t = ev["params"]["targetInfo"].get("type")
                    print(f"[rawcdp] attached type={t} sid={sid[:8]}")
                    if t in ("page", "iframe", "worker", "other"):
                        setup_session(cdp, sid)
                elif m == "Debugger.paused":
                    sid = ev.get("sessionId")
                    n_pause += 1
                    frames = ev.get("params", {}).get("callFrames", [])
                    print(f"[rawcdp] 暂停#{n_pause} sid={sid[:8] if sid else '?'} "
                          f"reason={ev['params'].get('reason')} frames={len(frames)}")
                    scan_paused(cdp, sid, ev.get("params", {}), found, deadline, pause_dump)
                    # 取栈顶各帧函数源码切片（读真实编码算法）
                    srcs, frame_src = {}, []
                    for fr in frames[:6]:
                        loc = fr.get("location", {})
                        scid = loc.get("scriptId")
                        col = loc.get("columnNumber", 0)
                        if scid and scid not in srcs:
                            mid = cdp.cmd("Debugger.getScriptSource", {"scriptId": scid}, sid=sid)
                            r = cdp.wait_resp(mid, deadline)
                            srcs[scid] = (r or {}).get("result", {}).get("scriptSource", "")
                        full = srcs.get(scid, "")
                        frame_src.append({"fn": fr.get("functionName"), "col": col,
                                          "src": full[max(0, col - 1800): col + 1800]})
                    json.dump(frame_src, open("_px_src.json", "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    cdp.cmd("Debugger.resume", sid=sid)
                    if pause_dump:
                        break
        cdp.cmd("Target.setAutoAttach", {"autoAttach": False, "flatten": True})
        print(f"[rawcdp] 事件统计: {seen_methods}  sessions={len(cdp.sessions)} pauses={n_pause}")
    finally:
        try:
            cdp.ws.close()
        except Exception:
            pass
        bb.close_browser(pid); bb.delete_browser(pid)

    json.dump(found, open("_px_alpha.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(pause_dump if 'pause_dump' in dir() else [], open("_px_pause_dump.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"[rawcdp] 候选字母表(48-72/uniq≥44) {len(found)} 个:")
    for s, n in sorted(found.items(), key=lambda x: -len(set(x[0]))):
        print(f"  uniq={len(set(s))} len={len(s)} hits={n}: {s}")
    try:
        pd = pause_dump
    except NameError:
        pd = []
    print(f"[rawcdp] 暂停态 dump：{len(pd)} 帧，已存 _px_pause_dump.json")
    for fr in pd:
        longs = {k: v for k, v in fr["vars"].items() if len(v) >= 40}
        print(f"  帧#{fr['i']} fn={fr['fn']!r} line={fr['line']} 长串变量={list(longs.keys())}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
