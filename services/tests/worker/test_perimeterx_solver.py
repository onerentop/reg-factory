import asyncio
import sys
import types
from worker.capabilities.captcha.perimeterx import PerimeterXHoldSolver
from worker.capabilities.interfaces import CaptchaService


class _FakePage:
    context = "CTX"


def test_is_captcha_service_kind_perimeterx():
    s = PerimeterXHoldSolver()
    assert isinstance(s, CaptchaService) and s.kind == "perimeterx"


def test_solve_wraps_root(monkeypatch):
    captured = {}

    async def fake_solve(page, context, idx=0, tag=""):
        captured["page"] = page
        captured["context"] = context
        captured["idx"] = idx
        return True

    root = types.ModuleType("register_outlook_standalone")
    root._solve_signup_captcha = fake_solve
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", root)

    page = _FakePage()
    ok = asyncio.run(PerimeterXHoldSolver().solve(page, {"idx": 3}))
    assert ok is True
    assert captured["page"] is page
    assert captured["context"] == "CTX"          # 取自 page.context
    assert captured["idx"] == 3


def test_solve_idx_defaults_zero(monkeypatch):
    captured = {}

    async def fake_solve(page, context, idx=0, tag=""):
        captured["idx"] = idx
        return False

    root = types.ModuleType("register_outlook_standalone")
    root._solve_signup_captcha = fake_solve
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", root)

    ok = asyncio.run(PerimeterXHoldSolver().solve(_FakePage(), {}))
    assert ok is False and captured["idx"] == 0
