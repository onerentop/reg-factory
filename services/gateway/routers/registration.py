import httpx as _httpx

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_schema import ApiResponse
from gateway.deps import get_session, _CONFIG_URL

router = APIRouter()


async def _pick_active_proxy(session: AsyncSession) -> str:
    """直接查 gateway.db 取一个 active 代理串。
    注册端点是 async + gateway 单 worker，绝不能用同步 requests 自调用
    /proxy(会阻塞事件循环 → 自调用排不进去超时 → proxy 空 → 注册直连)，
    故直接查库，零 HTTP 自调用。"""
    import random
    from sqlalchemy import select
    from gateway.models import ProxyEntry
    result = await session.execute(select(ProxyEntry))
    avail = [p for p in result.scalars().all() if p.status in ("active", "available")]
    if not avail:
        return ""
    p = random.choice(avail)
    auth = f"{p.username}:{p.password}@" if p.username and p.password else ""
    return f"{p.type or 'socks5'}://{auth}{p.host}:{p.port}"


@router.post("/register/{platform}", response_model=ApiResponse)
async def trigger_registration(platform: str, body: dict = {}, session: AsyncSession = Depends(get_session)):
    """从前端触发注册(platform=outlook/google)，分发到对应 flow。multiprocessing 真并发。"""
    from worker.process_manager import task_manager
    from worker.tasks._helpers import rotate_proxy_sid
    count = body.get("count", 1)
    proxy = body.get("proxy", "")
    config = dict(body.get("config", {}) or {})
    # 注册模式：优先取 body 顶层 mode（前端下拉），回退 config.mode，默认 browser
    from gateway.registration_helpers import resolve_registration_mode
    config["mode"] = resolve_registration_mode(body)
    if platform == "google":
        try:
            async with _httpx.AsyncClient(timeout=5, trust_env=False) as c:
                r = await c.get(f"{_CONFIG_URL}/config/gmail_sms_config")
                val = (r.json().get("data") or {}).get("value")
                if isinstance(val, dict):
                    config["sms"] = val
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("gmail_sms_config 拉取失败，跳过接码配置注入: %s", e)
    if not proxy:
        proxy = await _pick_active_proxy(session)
    task_ids = []
    for i in range(count):
        # 每个并发窗口轮换 sid → 不同出口 IP，避免 PerimeterX 因同 IP 关联多账号
        tid = task_manager.submit(idx=i, proxy=rotate_proxy_sid(proxy), config=config, platform=platform)
        task_ids.append(tid)
    return ApiResponse(data={"task_ids": task_ids, "status": "running", "count": count})


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task_status(task_id: str):
    """查询任务状态（进程管理器）。"""
    from worker.process_manager import task_manager
    data = task_manager.get_status(task_id)
    return ApiResponse(data=data)
