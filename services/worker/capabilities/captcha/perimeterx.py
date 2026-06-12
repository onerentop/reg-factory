"""PerimeterXHoldSolver：包根 _solve_signup_captcha(预热+9-12s长按+Arkose兜底)，原生 captcha 能力。

kind='perimeterx'(Outlook 主验证码=PerimeterX 长按)。不改根；惰性 import 根函数。

注：根 `_solve_signup_captcha` 由里程碑2b Task 2 抽取产出。本能力类与单测(monkeypatch)先就位；
真正接进 default_outlook_bundle + 生产调用待 Task 2 根函数落地后（见
docs/superpowers/plans/2026-06-12-outlook-nativeization-milestone2b.md）。
"""

from worker.capabilities.interfaces import CaptchaService


class PerimeterXHoldSolver(CaptchaService):
    kind = "perimeterx"

    async def solve(self, page, context: dict) -> bool:
        from register_outlook_standalone import _solve_signup_captcha
        idx = (context or {}).get("idx", 0)
        return await _solve_signup_captcha(page, page.context, idx)
