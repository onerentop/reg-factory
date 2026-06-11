from perimeterx_solver.analysis.payload_tracer import PayloadTracer


def test_correlates_json_then_egress():
    # hook 事件流：先 json(明文) 再 egress(密文出口)
    events = [
        {"kind": "json", "data": {"head": '{"PX123":1,"mouse":[]}', "len": 50}, "t": 1.0},
        {"kind": "btoa", "data": {"head": "ZW5j", "len": 400}, "t": 1.1},
        {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "payload=ZW5j..."}, "t": 1.2},
    ]
    tp = PayloadTracer().trace(events)
    assert tp is not None
    assert "mouse" in tp.plaintext_head
    assert tp.egress_url.endswith("/collector")


def test_no_egress_returns_none():
    assert PayloadTracer().trace([{"kind": "json", "data": {"head": "{}", "len": 2}, "t": 1.0}]) is None
