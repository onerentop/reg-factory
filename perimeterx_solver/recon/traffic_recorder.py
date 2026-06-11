# perimeterx_solver/recon/traffic_recorder.py
from ..classify import is_px_url, classify_px_url, parse_collector_body, PxKind
from ..models import CapturedRequest


class PxTrafficRecorder:
    """缓冲 PX 域请求并解析 collector 载荷。活体 CDP 事件经 on_request_finished 注入。"""

    def __init__(self):
        self.captured = []  # list[CapturedRequest]

    def on_request_finished(self, url, method, req_body, status, resp_body, headers, ts):
        if not is_px_url(url):
            return
        self.captured.append(CapturedRequest(
            url=url, method=method, req_body=req_body or "",
            resp_status=status, resp_body=resp_body or "",
            req_headers=dict(headers or {}), resp_headers={}, ts=ts,
        ))

    def collector_payloads(self):
        out = []
        for c in sorted(self.captured, key=lambda r: r.ts):
            if classify_px_url(c.url, c.method) == PxKind.COLLECTOR:
                out.append(parse_collector_body(c.req_body))
        return out
