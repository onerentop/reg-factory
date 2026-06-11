# tests/perimeterx_solver/test_classify.py
from perimeterx_solver.classify import is_px_url, classify_px_url, parse_collector_body, PxKind


def test_is_px_url():
    assert is_px_url("https://PXzC5j78di.px-cdn.net/api/v2/collector")
    assert is_px_url("https://collector-PXzC5j78di.px-cloud.net/api/v1/collector")
    assert is_px_url("https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di")
    assert not is_px_url("https://signup.live.com/API/CreateAccount")


def test_classify_px_url():
    assert classify_px_url("https://PXzC5j78di.px-cdn.net/api/v2/collector", "POST") == PxKind.COLLECTOR
    # 实测 MS 真端点：collector- 主机名 + /api/v2/msft 路径（不含 "collector"）
    assert classify_px_url("https://collector-pxzc5j78di.hsprotect.net/api/v2/msft", "POST") == PxKind.COLLECTOR
    assert classify_px_url("https://client.px-cloud.net/PXzC5j78di/main.min.js", "GET") == PxKind.SCRIPT
    assert classify_px_url("https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di", "GET") == PxKind.CHALLENGE_IFRAME
    assert classify_px_url("https://x.px-cdn.net/favicon.ico", "GET") == PxKind.OTHER


def test_parse_collector_form_body():
    body = "payload=ZW5jcnlwdGVk&appId=PXzC5j78di&tag=mobile&uuid=u-1&ft=2&pxhd=hd-1"
    p = parse_collector_body(body)
    assert p.encrypted_blob == "ZW5jcnlwdGVk"
    assert p.plaintext_fields["appId"] == "PXzC5j78di"
    assert p.plaintext_fields["uuid"] == "u-1"


def test_parse_collector_json_body():
    body = '{"payload":"ZW5j","appId":"PXzC5j78di","uuid":"u-2"}'
    p = parse_collector_body(body)
    assert p.encrypted_blob == "ZW5j"
    assert p.plaintext_fields["uuid"] == "u-2"
