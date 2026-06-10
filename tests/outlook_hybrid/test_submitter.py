from unittest.mock import MagicMock
import pytest
import requests
from outlook_hybrid.submitter import ProtocolSubmitter
from outlook_hybrid.credential import MintedCredential
from outlook_hybrid.errors import SubmitRejected


def _cred():
    return MintedCredential(
        cookies=[{"name": "_px3", "value": "v", "domain": ".live.com", "path": "/"}],
        canary="can1",
        create_payload={"MemberName": "u@outlook.com", "Password": "Pw!1", "HSol": "tok"},
        request_headers={"canary": "can1", "hpgid": "200225", "scid": "100118"},
        user_agent="UA/1.0",
        proxy="",
        captured=True,
    )


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text

    def json(self):
        import json
        return json.loads(self.text)


def _session_with(post_fn):
    s = MagicMock()
    s.headers = {}
    s.cookies = requests.Session().cookies
    s.post = post_fn
    return s


def _session_returning(resp):
    def _post(url, json=None, headers=None, proxies=None, timeout=None):
        return resp
    return _session_with(_post)


def test_success_replays_and_verifies_and_extracts():
    sent = {}

    def fake_post(url, json=None, headers=None, proxies=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        sent["headers"] = headers
        return _FakeResp(200, '{"ok": true}')

    sub = ProtocolSubmitter(
        token_extractor=lambda email, password, proxy: "refresh_xyz",
        verifier=lambda email, password, tag="": True,
    )
    sub._session_factory = lambda: _session_with(fake_post)

    res = sub.submit(_cred())
    assert res.success is True
    assert res.email == "u@outlook.com"
    assert res.refresh_token == "refresh_xyz"
    assert sent["url"].endswith("/API/CreateAccount?lic=1")
    assert sent["json"]["HSol"] == "tok"
    assert sent["headers"]["canary"] == "can1"


def test_ms_error_raises_submit_rejected():
    sub = ProtocolSubmitter(
        token_extractor=lambda *a, **k: "",
        verifier=lambda *a, **k: True,
    )
    sub._session_factory = lambda: _session_returning(
        _FakeResp(200, '{"error": {"code": "1304", "data": "challenge"}}'))
    with pytest.raises(SubmitRejected):
        sub.submit(_cred())


def test_success_without_token_still_success():
    sub = ProtocolSubmitter(
        token_extractor=lambda *a, **k: "",   # 抽不到 token
        verifier=lambda *a, **k: True,
    )
    sub._session_factory = lambda: _session_returning(_FakeResp(200, '{"ok": true}'))
    res = sub.submit(_cred())
    assert res.success is True
    assert res.refresh_token == ""
    assert res.has_token is False
