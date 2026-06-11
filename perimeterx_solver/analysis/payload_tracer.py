from ..classify import is_px_url
from ..models import TracedPayload

_EGRESS = ("egress_xhr", "egress_fetch")
_ENCODE = ("json", "btoa")


class PayloadTracer:
    """从 hook 事件流关联：最近一次明文(json) + 编码链 → 打到 collector 的出口。"""

    def trace(self, events):
        events = sorted(events, key=lambda e: e.get("t", 0))
        egress = next((e for e in events
                       if e["kind"] in _EGRESS and is_px_url(e["data"].get("url", ""))
                       and "/collector" in e["data"].get("url", "")), None)
        if not egress:
            return None
        t = egress["t"]
        before = [e for e in events if e.get("t", 0) <= t and e["kind"] in _ENCODE]
        json_ev = next((e for e in reversed(before) if e["kind"] == "json"), None)
        return TracedPayload(
            egress_url=egress["data"]["url"],
            egress_body_head=egress["data"].get("body", "")[:120],
            plaintext_head=(json_ev["data"]["head"] if json_ev else ""),
            encoding_chain=[e["kind"] for e in before],
        )
