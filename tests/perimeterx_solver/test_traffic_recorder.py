# tests/perimeterx_solver/test_traffic_recorder.py
from perimeterx_solver.recon.traffic_recorder import PxTrafficRecorder


def test_records_only_px_and_parses_collector():
    rec = PxTrafficRecorder()
    rec.on_request_finished("https://signup.live.com/x", "GET", "", 200, "", {}, 1.0)  # 丢弃
    rec.on_request_finished("https://PXzC5j78di.px-cdn.net/api/v2/collector", "POST",
                            "payload=ZW5j&appId=PXzC5j78di&uuid=u1", 200, "{}", {}, 2.0)
    assert len(rec.captured) == 1
    cap = rec.captured[0]
    assert cap.url.endswith("/collector")
    # collector 解析结果挂在 recorder 上，供协议图用
    cps = rec.collector_payloads()
    assert cps[0].plaintext_fields["uuid"] == "u1"
    assert cps[0].encrypted_blob == "ZW5j"


def test_collector_payloads_in_order():
    rec = PxTrafficRecorder()
    for i, ts in enumerate((1.0, 2.0)):
        rec.on_request_finished("https://PXzC5j78di.px-cdn.net/api/v2/collector", "POST",
                                f"payload=p{i}&appId=A", 200, "", {}, ts)
    assert [c.encrypted_blob for c in rec.collector_payloads()] == ["p0", "p1"]
