"""Outlook 混合注册：浏览器铸会话 → 协议提交。

对外入口：register_outlook_hybrid(proxy_str, idx) -> (email, password, refresh_token) | (None, None)
"""

import os

from .minter import SessionMinter
from .submitter import ProtocolSubmitter, RegistrationResult
from .fallback import FallbackPolicy
from .pool import BrowserPool
from .orchestrator import HybridOutlookOrchestrator

__all__ = ["register_outlook_hybrid"]

# 单进程内全局浏览器池（铸 token 阶段限流）
_POOL = BrowserPool(int(os.environ.get("HYBRID_BROWSER_CONCURRENCY", "2")))


def _extract_token(email, password, proxy):
    """从已建号会话抽 refresh_token。

    注：混合模式建号后，token 由独立的 /tools/extract-graph-token 流程补齐，
    这里返回空字符串不阻断成功（has_token=false）。后续可接入 HTTP 抽取。
    """
    return ""


def _build_orchestrator():
    from common.browser_provider import get_browser_provider
    from register_outlook_standalone import verify_registered_outlook, _register_one_browser

    bb = get_browser_provider()
    minter = SessionMinter(bb)
    submitter = ProtocolSubmitter(token_extractor=_extract_token, verifier=verify_registered_outlook)

    async def _browser_fallback(proxy, idx):
        result = await _register_one_browser(bb, idx, proxy)
        if result and len(result) >= 2 and result[0]:
            token = result[2] if len(result) > 2 else ""
            return RegistrationResult(success=True, email=result[0], password=result[1],
                                      refresh_token=token or "", mode_used="browser_fallback")
        return RegistrationResult(success=False, error="browser fallback failed",
                                  mode_used="browser_fallback")

    async def _hybrid_retry(proxy, idx):
        cred = await minter.mint(proxy, idx)
        return submitter.submit(cred)

    fallback = FallbackPolicy(browser_fallback=_browser_fallback, hybrid_retry=_hybrid_retry)
    return HybridOutlookOrchestrator(minter=minter, submitter=submitter, fallback=fallback, pool=_POOL)


async def register_outlook_hybrid(proxy_str, idx=0):
    """混合注册入口。返回 (email, password, refresh_token) 或 (None, None)。"""
    orch = _build_orchestrator()
    res = await orch.register(proxy_str, idx)
    if res.success and res.email:
        return res.email, res.password, res.refresh_token
    return None, None
