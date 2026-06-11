from perimeterx_solver.analysis.instrumented_session import InstrumentationResult


def test_result_runs_tracer_and_locator():
    events = [
        {"kind": "json", "data": {"head": '{"a":1,"mouse":[]}', "len": 30}, "t": 1.0},
        {"kind": "btoa", "data": {"head": "ZW5j", "len": 300}, "t": 1.1},
        {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "payload=ZW5j"}, "t": 1.2},
    ]
    r = InstrumentationResult.from_events(events)
    assert r.traced.egress_url.endswith("/collector")
    assert "base64" in r.crypto.kinds
    assert r.event_count == 3
