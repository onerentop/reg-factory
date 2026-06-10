from outlook_hybrid.credential import MintedCredential


def _sample():
    return MintedCredential(
        cookies=[{"name": "_px3", "value": "abc", "domain": ".live.com", "path": "/"}],
        canary="canary123",
        create_payload={"MemberName": "user@outlook.com", "Password": "Pw!12345", "HSol": "tok"},
        request_headers={"canary": "canary123", "hpgid": "200225"},
        user_agent="UA/1.0",
        proxy="http://1.2.3.4:8080",
        captured=True,
    )


def test_email_and_password_read_from_payload():
    c = _sample()
    assert c.email == "user@outlook.com"
    assert c.password == "Pw!12345"


def test_has_token_true_when_hsol_present():
    assert _sample().has_token is True


def test_has_token_false_when_hsol_missing():
    c = _sample()
    c.create_payload = {"MemberName": "x@outlook.com", "Password": "p"}
    assert c.has_token is False
