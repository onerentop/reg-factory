from fastapi import APIRouter

from shared.base_schema import ApiResponse

router = APIRouter()


@router.post("/register/outlook", response_model=ApiResponse)
async def trigger_outlook_registration(body: dict = {}):
    """从前端触发 Outlook 注册。用 multiprocessing 真并发。"""
    from worker.process_manager import task_manager, _fetch_proxy_from_manager
    count = body.get("count", 1)
    proxy = body.get("proxy", "")
    config = dict(body.get("config", {}) or {})
    # 注册模式：优先取 body 顶层 mode（前端下拉），回退 config.mode，默认 browser
    from gateway.registration_helpers import resolve_registration_mode
    config["mode"] = resolve_registration_mode(body)
    if not proxy:
        proxy = _fetch_proxy_from_manager()
    task_ids = []
    for i in range(count):
        tid = task_manager.submit(idx=i, proxy=proxy, config=config)
        task_ids.append(tid)
    return ApiResponse(data={"task_ids": task_ids, "status": "running", "count": count})


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task_status(task_id: str):
    """查询任务状态（进程管理器）。"""
    from worker.process_manager import task_manager
    data = task_manager.get_status(task_id)
    return ApiResponse(data=data)
