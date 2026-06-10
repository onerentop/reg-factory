"""编排：浏览器铸凭证（占浏览器槽）→ 协议立即 replay（不占浏览器）→ 失败回退。"""

from .errors import MintFailed, SubmitRejected
from .submitter import RegistrationResult


class HybridOutlookOrchestrator:
    def __init__(self, minter, submitter, fallback, pool):
        self._minter = minter
        self._submitter = submitter
        self._fallback = fallback
        self._pool = pool

    async def register(self, proxy: str, idx: int = 0) -> RegistrationResult:
        try:
            async with self._pool.slot():
                cred = await self._minter.mint(proxy, idx)   # 仅此阶段占浏览器
            result = self._submitter.submit(cred)             # 协议侧，无浏览器
            if result.success:
                return result
            raise SubmitRejected(result.error or "submit failed")
        except (MintFailed, SubmitRejected) as e:
            return await self._fallback.handle(proxy, idx, e)
