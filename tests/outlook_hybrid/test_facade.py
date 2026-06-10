import asyncio
import inspect
import outlook_hybrid


def test_facade_exported():
    assert hasattr(outlook_hybrid, "register_outlook_hybrid")


def test_extract_token_returns_refresh_token(monkeypatch):
    monkeypatch.setattr("extract_graph_tokens.get_graph_token",
                        lambda email, password, *a, **k: {"refresh_token": "RT123"})
    assert outlook_hybrid._extract_token("e@x.com", "pw", "") == "RT123"


def test_extract_token_safe_on_failure(monkeypatch):
    monkeypatch.setattr("extract_graph_tokens.get_graph_token", lambda *a, **k: None)
    assert outlook_hybrid._extract_token("e@x.com", "pw", "") == ""


def test_facade_is_async_with_expected_signature():
    fn = outlook_hybrid.register_outlook_hybrid
    assert inspect.iscoroutinefunction(fn)
    params = list(inspect.signature(fn).parameters)
    assert params[:2] == ["proxy_str", "idx"]


def test_facade_returns_tuple_via_orchestrator(monkeypatch):
    from outlook_hybrid.submitter import RegistrationResult

    class _FakeOrch:
        def __init__(self, *a, **k): pass
        async def register(self, proxy, idx):
            return RegistrationResult(success=True, email="x@outlook.com",
                                      password="Pw!", refresh_token="rt", mode_used="hybrid")

    monkeypatch.setattr("outlook_hybrid.HybridOutlookOrchestrator", _FakeOrch)
    res = asyncio.run(outlook_hybrid.register_outlook_hybrid("proxy", 0))
    assert res == ("x@outlook.com", "Pw!", "rt")


def test_facade_returns_none_on_failure(monkeypatch):
    from outlook_hybrid.submitter import RegistrationResult

    class _FakeOrch:
        def __init__(self, *a, **k): pass
        async def register(self, proxy, idx):
            return RegistrationResult(success=False, error="all failed")

    monkeypatch.setattr("outlook_hybrid.HybridOutlookOrchestrator", _FakeOrch)
    res = asyncio.run(outlook_hybrid.register_outlook_hybrid("proxy", 0))
    assert res == (None, None)
