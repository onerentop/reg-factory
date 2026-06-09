from shared.captcha.base import CaptchaSolver, CaptchaType, CaptchaResult
from shared.captcha.capsolver import CapSolverClient
from shared.captcha.ezcaptcha import EzCaptchaClient

SOLVER_REGISTRY: dict[str, type[CaptchaSolver]] = {
    "capsolver": CapSolverClient,
    "ezcaptcha": EzCaptchaClient,
}

__all__ = ["CaptchaSolver", "CaptchaType", "CaptchaResult", "CapSolverClient", "EzCaptchaClient", "SOLVER_REGISTRY"]
