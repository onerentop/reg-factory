"""EZ-Captcha 集成。从 register_outlook_standalone.py 迁移。"""

import asyncio
import httpx
from shared.captcha.base import CaptchaSolver, CaptchaResult


class EzCaptchaClient(CaptchaSolver):
    name = "ezcaptcha"

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self._base_url = kwargs.get("base_url", "https://api.ez-captcha.com")

    async def solve_arkose(self, public_key: str, page_url: str, **kwargs) -> CaptchaResult:
        return await self._submit_and_poll({
            "clientKey": self._api_key,
            "task": {"type": "FunCaptchaTaskProxyLess", "websitePublicKey": public_key, "websiteURL": page_url},
        }, kwargs.get("max_wait", 120))

    async def solve_recaptcha(self, site_key: str, page_url: str, **kwargs) -> CaptchaResult:
        return await self._submit_and_poll({
            "clientKey": self._api_key,
            "task": {"type": "ReCaptchaV2TaskProxyLess", "websiteKey": site_key, "websiteURL": page_url},
        }, kwargs.get("max_wait", 120))

    async def _submit_and_poll(self, payload: dict, max_wait: int) -> CaptchaResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._base_url}/createTask", json=payload)
            data = resp.json()
            if data.get("errorId", 1) != 0:
                return CaptchaResult(success=False, error=data.get("errorDescription", "Unknown"))
            task_id = data.get("taskId")
            if not task_id:
                return CaptchaResult(success=False, error="No task ID")
            elapsed = 0
            while elapsed < max_wait:
                await asyncio.sleep(5)
                elapsed += 5
                resp = await client.post(f"{self._base_url}/getTaskResult", json={"clientKey": self._api_key, "taskId": task_id})
                result = resp.json()
                if result.get("status") == "ready":
                    return CaptchaResult(success=True, token=result.get("solution", {}).get("token", ""))
                if result.get("status") == "failed":
                    return CaptchaResult(success=False, error=result.get("errorDescription", ""))
        return CaptchaResult(success=False, error="Timeout")
