# tests/perimeterx_solver/test_models.py
from perimeterx_solver.models import CapturedRequest, CookieSnapshot, Sample


def test_captured_request_roundtrip():
    r = CapturedRequest(url="https://PXzC5j78di.px-cdn.net/api/v2/collector",
                        method="POST", req_body="payload=abc&appId=PXzC5j78di",
                        resp_status=200, resp_body="{}", req_headers={}, resp_headers={}, ts=1.0)
    d = r.to_dict()
    assert d["url"].endswith("/api/v2/collector")
    assert CapturedRequest.from_dict(d).method == "POST"


def test_sample_outcome_validation():
    s = Sample(run_id="r1", outcome="pass")
    assert s.outcome == "pass"
    assert s.requests == [] and s.cookie_snapshots == []
    import pytest
    with pytest.raises(ValueError):
        Sample(run_id="r2", outcome="bogus")
