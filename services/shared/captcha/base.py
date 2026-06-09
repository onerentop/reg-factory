from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass


class CaptchaType(Enum):
    ARKOSE = "arkose"
    RECAPTCHA = "recaptcha"
    PERIMETERX = "perimeterx"
    HCAPTCHA = "hcaptcha"


@dataclass
class CaptchaResult:
    success: bool
    token: str = ""
    error: str = ""


class CaptchaSolver(ABC):
    """验证码求解器抽象基类。策略模式。"""

    name: str = ""

    def __init__(self, api_key: str, **kwargs):
        self._api_key = api_key
        self._extra = kwargs

    @abstractmethod
    async def solve_arkose(self, public_key: str, page_url: str, **kwargs) -> CaptchaResult: ...

    @abstractmethod
    async def solve_recaptcha(self, site_key: str, page_url: str, **kwargs) -> CaptchaResult: ...

    async def solve_perimeterx(self, page_url: str, **kwargs) -> CaptchaResult:
        return CaptchaResult(success=False, error="Not supported")
