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


@router.post("/register/{platform}", response_model=ApiResponse)
async def trigger_registration(
    platform: str,
    body: RegistrationRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """先持久化任务，再交给本机有界子进程池执行。"""
    from gateway.registration_helpers import resolve_registration_mode
    from gateway.registration_jobs import RegistrationJobService
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

            config_service = ConfigService(
                ConfigRepository(session), ConfigVersionRepository(session)
            )
            entry = await config_service.get("gmail_sms_config")
            if entry is not None and isinstance(entry.value, dict):
                config["sms"] = entry.value
        except Exception as error:
            import logging
            logging.getLogger(__name__).warning("gmail_sms_config 拉取失败，跳过接码配置注入: %s", error)

    # 「当天一 IP 一窗口」：代理不再在循环外解析一次共享给整批，
    # 而是每个任务各抢一个当天未被占用的 IP。
    from gateway.proxy_binding_service import ACTIVE_STATUSES, ProxyBindingService

    # 裸连接串指向的代理在库里没有 ProxyEntry 记录，绑不上任何 binding，
    # 等于给「当天一 IP 一窗口」开了一道后门，故直接拒绝。
    # schema 里保留 proxy 字段是为了让调用方拿到这条明确可执行的 422，
    # 而不是字段被静默忽略后再去猜为什么代理没生效。
    if body.proxy:
        raise HTTPException(
            status_code=422,
            detail="不再支持直接传 proxy 连接串，请先把代理录入代理池后用 proxy_id 指定",
        )

    binding_service = ProxyBindingService(session)

    if body.proxy_id:
        if body.count > 1:
            raise HTTPException(status_code=422, detail="手动指定代理时数量只能为 1")
        selected = await binding_service.get_proxy(body.proxy_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="Proxy not found")
        if selected.status not in ACTIVE_STATUSES:
            raise HTTPException(status_code=422, detail="该代理当前不可用")

    job_service = RegistrationJobService(session)
    task_ids: list[str] = []
    skipped = 0
    for index in range(body.count):
        task_id = str(uuid.uuid4())
        if body.proxy_id:
            claim = await binding_service.claim_specific(body.proxy_id, task_id, platform)
            if claim is None:
                raise HTTPException(status_code=409, detail="该代理今日已绑定窗口")
            proxy_url = claim.proxy_url
        else:
            claim = await binding_service.claim(task_id, platform)
            if claim is None:
                skipped = body.count - index      # 池子见底，已派发的照常跑
                break
            proxy_url = claim.proxy_url

        await job_service.enqueue(task_id, platform)
        # binding 与 queued Job 必须同事务提交，否则「抢到 IP 但任务没落库」会留下
        # 永不回收的悬挂占用。提交后子进程事件才能安全地由独立会话更新该 Job。
        if session is not None:
            await session.commit()
        await runtime.submit_registration(
            task_id,
            platform=platform,
            idx=index,
            proxy=proxy_url,
            config=config,
        )
        task_ids.append(task_id)

    return ApiResponse(
        data={
            "task_ids": task_ids,
            "status": "queued",
            "count": body.count,
            "dispatched": len(task_ids),
            "skipped": skipped,
            "message": (
                f"当天可用 IP 不足，已启动 {len(task_ids)}/{body.count}" if skipped else None
            ),
        }
    )


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
