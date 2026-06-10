import asyncio
import pytest
from outlook_hybrid.fallback import FallbackPolicy
from outlook_hybrid.submitter import RegistrationResult
from outlook_hybrid.errors import MintFailed, SubmitRejected


def _run(coro):
    return asyncio.run(coro)


def test_submit_rejected_falls_back_to_browser():
    calls = {}

    async def fake_browser(proxy, idx):
        calls["browser"] = True
        return RegistrationResult(success=True, email="b@outlook.com", mode_used="browser_fallback")

    pol = FallbackPolicy(browser_fallback=fake_browser, hybrid_retry=None)
    res = _run(pol.handle("proxy", 0, SubmitRejected("token rejected")))
    assert res.success is True
    assert res.mode_used == "browser_fallback"
    assert calls.get("browser") is True


def test_mint_failed_retries_hybrid_once_then_browser():
    seq = []

    async def fake_retry(proxy, idx):
        seq.append("retry")
        raise MintFailed("still failing")

    async def fake_browser(proxy, idx):
        seq.append("browser")
        return RegistrationResult(success=True, mode_used="browser_fallback")

    pol = FallbackPolicy(browser_fallback=fake_browser, hybrid_retry=fake_retry)
    res = _run(pol.handle("proxy", 0, MintFailed("first fail")))
    assert seq == ["retry", "browser"]
    assert res.success is True


def test_browser_fallback_failure_returns_unsuccessful():
    async def fake_browser(proxy, idx):
        return RegistrationResult(success=False, error="browser also failed", mode_used="browser_fallback")

    pol = FallbackPolicy(browser_fallback=fake_browser, hybrid_retry=None)
    res = _run(pol.handle("proxy", 0, SubmitRejected("x")))
    assert res.success is False
