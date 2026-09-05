from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.deps import get_session
from gateway.schemas import RegistrationRequest
from shared.base_schema import ApiResponse

router = APIRouter()
SUPPORTED_PLATFORMS = frozenset({"outlook", "google"})
SUPPORTED_MODES = {
    "outlook": frozenset({"browser", "hybrid", "protocol"}),
    "google": frozenset({"browser"}),
}


def _proxy_url(proxy) -> str:
    """仅在服务端将代理记录组装为连接串，密码绝不返回浏览器。"""
    auth = f"{proxy.username}:{proxy.password}@" if proxy.username and proxy.password else ""
    return f"{proxy.type or 'socks5'}://{auth}{proxy.host}:{proxy.port}"


async def _pick_active_proxy(session: AsyncSession) -> str:
    """从代理池取一个可用代理（active/available/slow）。"""
    import random
    from sqlalchemy import select
    from gateway.models import ProxyEntry
    result = await session.execute(select(ProxyEntry))
    available = [p for p in result.scalars().all() if p.status in ("active", "available", "slow")]
    return _proxy_url(random.choice(available)) if available else ""


async def _resolve_proxy(session: AsyncSession, proxy_id: str | None, proxy: str) -> str:
    """proxy_id 优先，其次显式 proxy 串，最后从池随机取活跃代理。"""
    if proxy_id:
        import uuid
        from sqlalchemy import select
        from gateway.models import ProxyEntry
        try:
            identifier = uuid.UUID(proxy_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid proxy_id") from error
        result = await session.execute(select(ProxyEntry).where(ProxyEntry.id == identifier))
        selected = result.scalar_one_or_none()
        if selected is None:
            raise HTTPException(status_code=404, detail="Proxy not found")
        return _proxy_url(selected)
    return proxy or (await _pick_active_proxy(session) if session is not None else "")


@router.post("/register/{platform}", response_model=ApiResponse)
async def trigger_registration(
    platform: str,
    body: RegistrationRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """先持久化任务，再交给本机有界子进程池执行；每窗口轮换 1024proxy sid。"""
    from gateway.registration_helpers import resolve_registration_mode
    from gateway.registration_jobs import RegistrationJobService
    from worker.tasks._helpers import rotate_proxy_sid  # 自举项目根路径后再引 common.proxy
    import uuid

    runtime = getattr(request.app.state, "task_manager", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="本机任务管理器尚未启动")
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=422, detail="Unsupported platform; use outlook or google")

    payload = body.model_dump()
    config = dict(body.config)
    mode = resolve_registration_mode(payload)
    if mode not in SUPPORTED_MODES[platform]:
        raise HTTPException(status_code=422, detail=f"Unsupported {platform} registration mode: {mode}")
    config["mode"] = mode

    if platform == "google":
        try:
            from config_service.repository import ConfigRepository, ConfigVersionRepository
            from config_service.service import ConfigService
            config_service = ConfigService(ConfigRepository(session), ConfigVersionRepository(session))
            entry = await config_service.get("gmail_sms_config")
            if entry is not None and isinstance(entry.value, dict):
                config["sms"] = entry.value
        except Exception as error:
            import logging
            logging.getLogger(__name__).warning("gmail_sms_config 拉取失败，跳过接码配置注入: %s", error)

    base_proxy = await _resolve_proxy(session, body.proxy_id, body.proxy)
    job_service = RegistrationJobService(session)
    task_ids: list[str] = []
    for index in range(body.count):
        task_id = str(uuid.uuid4())
        await job_service.enqueue(task_id, platform)
        if session is not None:
            await session.commit()
        await runtime.submit_registration(
            task_id, platform=platform, idx=index,
            proxy=rotate_proxy_sid(base_proxy),  # 每窗口不同 sid → 不同出口 IP
            config=config,
        )
        task_ids.append(task_id)
    return ApiResponse(data={"task_ids": task_ids, "status": "queued", "count": body.count})


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task_status(task_id: str, session: AsyncSession = Depends(get_session)):
    """任务状态唯一来自 SQLite 持久化投影，不回退任何外部队列 backend。"""
    from gateway.registration_jobs import RegistrationJobService, serialize_job

    persisted_job = await RegistrationJobService(session).get_by_task_id(task_id)
    if persisted_job is None:
        return ApiResponse(data={"task_id": task_id, "status": "unknown"})
    return ApiResponse(data=serialize_job(persisted_job))


@router.get("/tasks/{task_id}/events", response_model=ApiResponse)
async def get_task_events(
    task_id: str,
    after: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """读取已提交的任务事件，供断线客户端按 seq 安全续传。"""
    from gateway.registration_jobs import RegistrationJobService, serialize_event

    service = RegistrationJobService(session)
    job = await service.get_by_task_id(task_id)
    if job is None:
        return ApiResponse(data={"task_id": task_id, "events": [], "next_seq": after, "has_more": False})
    events, has_more = await service.list_events(task_id, after=after, limit=limit)
    next_seq = events[-1].seq if events else max(after, 0)
    return ApiResponse(
        data={
            "task_id": task_id,
            "events": [serialize_event(event) for event in events],
            "next_seq": next_seq,
            "has_more": has_more,
        }
    )
