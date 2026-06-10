"""混合失败时的回退决策（Strategy）。"""

from .errors import MintFailed, SubmitRejected
from .submitter import RegistrationResult


class FallbackPolicy:
    """注入回退动作，便于测试。

    browser_fallback(proxy, idx) -> RegistrationResult（完整浏览器模式）
    hybrid_retry(proxy, idx) -> RegistrationResult（换会话重试混合；可为 None 跳过）
    """

    def __init__(self, browser_fallback, hybrid_retry=None):
        self._browser = browser_fallback
        self._retry = hybrid_retry

    async def handle(self, proxy, idx, error) -> RegistrationResult:
        # MintFailed 且配了重试：先换会话重试一次混合
        if isinstance(error, MintFailed) and self._retry is not None:
            try:
                return await self._retry(proxy, idx)
            except (MintFailed, SubmitRejected):
                pass  # 重试仍失败 → 落到浏览器回退
        # 其余情况（含 SubmitRejected、重试失败）→ 完整浏览器模式
        return await self._browser(proxy, idx)
