from perimeterx_solver.analysis.crypto_locator import CryptoLocator


def test_detects_base64_when_btoa_precedes_egress():
    events = [
        {"kind": "btoa", "data": {"head": "ZW5j", "len": 400}, "t": 1.0},
        {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "payload=ZW5j"}, "t": 1.1},
    ]
    f = CryptoLocator().locate(events)
    assert "base64" in f.kinds


def test_detects_subtle_crypto():
    events = [{"kind": "subtle_encrypt", "data": {"algo": "AES-CBC"}, "t": 1.0},
              {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "x"}, "t": 1.1}]
    f = CryptoLocator().locate(events)
    assert "aes" in f.kinds
