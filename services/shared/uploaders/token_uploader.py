"""Token 上传器。从 upload_tokens.py 迁移。支持 CPA/SUB2API/webchat2api。"""

import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TokenUploader:
    """通用 Token 上传器。支持多个下游目标。"""

    def __init__(self):
        self._targets: dict[str, dict] = {}
        self._uploaded: set[str] = set()

    def add_target(self, name: str, url: str, auth: dict | None = None) -> None:
        self._targets[name] = {"url": url, "auth": auth or {}}

    async def upload(self, target: str, payload: dict[str, Any]) -> dict:
        if target not in self._targets:
            return {"success": False, "error": f"Unknown target: {target}"}

        key = f"{target}:{payload.get('email', '')}"
        if key in self._uploaded:
            return {"success": True, "skipped": True}

        config = self._targets[target]
        headers = {"Content-Type": "application/json"}
        if config["auth"].get("bearer"):
            headers["Authorization"] = f"Bearer {config['auth']['bearer']}"

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(config["url"], json=payload, headers=headers)
                if resp.status_code < 400:
                    self._uploaded.add(key)
                    return {"success": True}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def upload_batch(self, target: str, payloads: list[dict]) -> list[dict]:
        results = []
        for p in payloads:
            r = await self.upload(target, p)
            results.append(r)
        return results
