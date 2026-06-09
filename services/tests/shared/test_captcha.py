from shared.captcha.base import CaptchaSolver, CaptchaType, CaptchaResult
from shared.captcha.capsolver import CapSolverClient
from shared.captcha.ezcaptcha import EzCaptchaClient


def test_captcha_types():
    assert CaptchaType.ARKOSE.value == "arkose"
    assert CaptchaType.RECAPTCHA.value == "recaptcha"
    assert CaptchaType.PERIMETERX.value == "perimeterx"

def test_capsolver_init():
    solver = CapSolverClient(api_key="test-key")
    assert solver.name == "capsolver"

def test_ezcaptcha_init():
    solver = EzCaptchaClient(api_key="test-key")
    assert solver.name == "ezcaptcha"

def test_solver_registry():
    from shared.captcha import SOLVER_REGISTRY
    assert "capsolver" in SOLVER_REGISTRY
    assert "ezcaptcha" in SOLVER_REGISTRY

def test_captcha_result():
    r = CaptchaResult(success=True, token="abc123")
    assert r.success is True
    assert r.token == "abc123"
