import asyncio
import sys
import types
from worker.capabilities.token import GraphTokenExtractor
from worker.capabilities.interfaces import EmailAccount, TokenExtractor


def _fake_root(extract_fn):
    mod = types.ModuleType("register_outlook_standalone")
    mod.extract_graph_token = extract_fn
    return mod


class _FakePage:
    context = "ctx-obj"


def test_is_token_extractor():
    assert isinstance(GraphTokenExtractor(), TokenExtractor)


def test_extract_wraps_graph_token(monkeypatch):
    captured = {}
    async def fake_extract(page, context, email, password, idx=0):
        captured["page"] = page
        captured["context"] = context
        captured["email"] = email
        captured["password"] = password
        return {"refresh_token": "rt", "client_id": "cid"}
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", _fake_root(fake_extract))
    page = _FakePage()
    acct = EmailAccount(email="e@x.com", password="pw")
    result = asyncio.run(GraphTokenExtractor().extract(page, acct))
    assert result == {"refresh_token": "rt", "client_id": "cid"}
    assert captured["page"] is page
    assert captured["context"] == "ctx-obj"           # 取自 page.context
    assert captured["email"] == "e@x.com" and captured["password"] == "pw"


def test_extract_none_becomes_empty_dict(monkeypatch):
    async def fake_extract(page, context, email, password, idx=0):
        return None
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", _fake_root(fake_extract))
    result = asyncio.run(GraphTokenExtractor().extract(_FakePage(), EmailAccount(email="e@x.com", password="pw")))
    assert result == {}
