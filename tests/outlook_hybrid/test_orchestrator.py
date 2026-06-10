import asyncio
import pytest
from outlook_hybrid.orchestrator import HybridOutlookOrchestrator
from outlook_hybrid.pool import BrowserPool
from outlook_hybrid.credential import MintedCredential
from outlook_hybrid.submitter import RegistrationResult
from outlook_hybrid.errors import MintFailed, SubmitRejected


def _run(coro):
    return asyncio.run(coro)


def _cred():
    return MintedCredential(
        create_payload={"MemberName": "u@outlook.com", "Password": "Pw!1", "HSol": "tok"},
        captured=True,
    )


class _Minter:
    def __init__(self, behavior):
        self._behavior = behavior  # "ok" | "mintfail"
    async def mint(self, proxy, idx=0):
        if self._behavior == "mintfail":
            raise MintFailed("no capture")
        return _cred()


class _Submitter:
    def __init__(self, behavior):
        self._behavior = behavior  # "ok" | "reject"
    def submit(self, cred):
        if self._behavior == "reject":
            raise SubmitRejected("rejected")
        return RegistrationResult(success=True, email=cred.email, refresh_token="rt", mode_used="hybrid")


class _Fallback:
    async def handle(self, proxy, idx, error):
        return RegistrationResult(success=True, email="fb@outlook.com", mode_used="browser_fallback")


def test_happy_path_returns_hybrid_result():
    orch = HybridOutlookOrchestrator(
        minter=_Minter("ok"), submitter=_Submitter("ok"),
        fallback=_Fallback(), pool=BrowserPool(2),
    )
    res = _run(orch.register("proxy", 0))
    assert res.success is True
    assert res.mode_used == "hybrid"
    assert res.email == "u@outlook.com"


def test_submit_reject_triggers_fallback():
    orch = HybridOutlookOrchestrator(
        minter=_Minter("ok"), submitter=_Submitter("reject"),
        fallback=_Fallback(), pool=BrowserPool(2),
    )
    res = _run(orch.register("proxy", 0))
    assert res.mode_used == "browser_fallback"
    assert res.success is True


def test_mint_fail_triggers_fallback():
    orch = HybridOutlookOrchestrator(
        minter=_Minter("mintfail"), submitter=_Submitter("ok"),
        fallback=_Fallback(), pool=BrowserPool(2),
    )
    res = _run(orch.register("proxy", 0))
    assert res.mode_used == "browser_fallback"


def test_browser_pool_limits_concurrency():
    pool = BrowserPool(1)
    order = []

    async def worker(n):
        async with pool.slot():
            order.append(f"enter{n}")
            await asyncio.sleep(0.05)
            order.append(f"exit{n}")

    async def _go():
        await asyncio.gather(worker(1), worker(2))

    _run(_go())
    # 并发=1 → 必须串行：enter1,exit1,enter2,exit2
    assert order == ["enter1", "exit1", "enter2", "exit2"]
