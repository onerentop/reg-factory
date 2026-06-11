# -*- coding: utf-8 -*-
"""🔴 原始 CDP（脱离 Playwright）提取 PerimeterX 自定义 base64 字母表。
直连 ixBrowser CDP → 建 page target → Debugger.enable + DOMDebugger.setXHRBreakpoint("collector")
→ Page.navigate(signup) → collector XHR 发送时暂停 → 遍历调用栈各帧 scopeChain →
Runtime.getProperties 扫"长度 50-70、独特字符多"的字符串(字母表通常是闭包常量)。
用法：python _px_rawcdp_alphabet.py "<proxy>"
"""
import json, sys, time
import websocket  # websocket-client
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from common.browser_provider import get_browser_provider

SIGNUP = "https://signup.live.com/signup?lic=1"


class RawCDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, max_size=None)
        self.ws.settimeout(60)
        self._id = 0
        self.paused = []          # 暂停事件队列
        self.events = []          # 其它事件

    def send(self, method, params=None, session_id=None, wait=True):
        self._id += 1
        mid = self._id
        msg = {"id": mid, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self.ws.send(json.dumps(msg))
        if not wait:
            return None
        return self._recv_until(lambda m: m.get("id") == mid)

    def _recv_until(self, pred, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(self.ws.recv())
            except Exception:
                break
            if m.get("method") == "Debugger.paused":
                self.paused.append(m)
            elif "method" in m:
                self.events.append(m)
            if pred(m):
                return m
        return None

    def wait_paused(self, timeout=45):
        if self.paused:
            return self.paused.pop(0)
        m = self._recv_until(lambda x: x.get("method") == "Debugger.paused", timeout)
        return self.paused.pop(0) if self.paused else m


def _looks(s):
    return isinstance(s, str) and 48 <= len(s) <= 72 and len(set(s)) >= 44


def main(proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_rawcdp", proxy_str=proxy)
    info = bb.open_browser(pid)
    ws_url = info.get("ws", "")
    print(f"[rawcdp] 连 {ws_url[:60]}...")
    found = {}
    cdp = RawCDP(ws_url)
    try:
        # 建 page target 并附着（flatten → sessionId）
        r = cdp.send("Target.createTarget", {"url": "about:blank"})
        tid = r["result"]["targetId"]
        r = cdp.send("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sid = r["result"]["sessionId"]
        cdp.send("Page.enable", session_id=sid)
        cdp.send("Debugger.enable", session_id=sid)
        cdp.send("DOMDebugger.setXHRBreakpoint", {"url": "collector"}, session_id=sid)
        cdp.send("Page.navigate", {"url": SIGNUP}, session_id=sid, wait=False)

        for attempt in range(4):
            p = cdp.wait_paused(timeout=45)
            if not p:
                print("[rawcdp] 未在超时内暂停")
                break
            frames = p.get("params", {}).get("callFrames", [])
            print(f"[rawcdp] 暂停 reason={p.get('params',{}).get('reason')} frames={len(frames)}")
            for fr in frames[:15]:
                for sc in fr.get("scopeChain", []):
                    oid = sc.get("object", {}).get("objectId")
                    if not oid:
                        continue
                    rp = cdp.send("Runtime.getProperties",
                                  {"objectId": oid, "ownProperties": True}, session_id=sid)
                    for prop in (rp or {}).get("result", {}).get("result", []):
                        v = prop.get("value", {}) or {}
                        if v.get("type") == "string" and _looks(v.get("value", "")):
                            found[v["value"]] = found.get(v["value"], 0) + 1
            if found:
                break
            cdp.send("Debugger.resume", session_id=sid, wait=False)
        cdp.send("Debugger.resume", session_id=sid, wait=False)
    finally:
        try:
            cdp.ws.close()
        except Exception:
            pass
        bb.close_browser(pid); bb.delete_browser(pid)

    print(f"[rawcdp] 候选字母表 {len(found)} 个:")
    for s, n in sorted(found.items(), key=lambda x: -len(set(x[0]))):
        print(f"  uniq={len(set(s))} len={len(s)}: {s}")
    json.dump(found, open("_px_alpha.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
