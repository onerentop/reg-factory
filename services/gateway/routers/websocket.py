from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.dependencies import jwt_strategy, settings

router = APIRouter()


async def _authenticate_websocket(websocket: WebSocket) -> bool:
    """使用 Sec-WebSocket-Protocol 传递短生命周期 JWT，避免令牌出现在 URL 日志中。"""
    if not settings.should_require_auth:
        return True
    offered_protocols = websocket.headers.get("sec-websocket-protocol", "")
    token = offered_protocols.split(",", 1)[0].strip()
    if token and jwt_strategy.verify(token).authenticated:
        return True
    await websocket.close(code=1008, reason="Unauthorized")
    return False


@router.websocket("/ws/task/{task_id}/logs")
async def task_logs_websocket(websocket: WebSocket, task_id: str):
    """回放 SQLite 已提交的注册任务事件，再推送该任务的实时事件。"""
    if not await _authenticate_websocket(websocket):
        return
    await websocket.accept()
    runtime = getattr(websocket.app.state, "task_manager", None)
    if runtime is None:
        await websocket.send_json({"type": "error", "message": "本机任务管理器尚未启动"})
        await websocket.close(code=1011)
        return

    try:
        after = max(int(websocket.query_params.get("after", "0")), 0)
    except ValueError:
        await websocket.send_json({"type": "error", "message": "after 必须是非负整数"})
        await websocket.close(code=1008)
        return

    subscription = runtime.subscribe(task_id)
    try:
        from app.core.dependencies import db
        from gateway.registration_jobs import RegistrationJobService, serialize_event_envelope

        async with db.get_session() as session:
            service = RegistrationJobService(session)
            job = await service.get_by_task_id(task_id)
            if job is None:
                await websocket.send_json({"type": "error", "message": "任务不存在"})
                return
            snapshot = {
                "task_id": job.task_id,
                "platform": job.platform,
                "status": job.status,
                "result": job.result,
                "error": job.error_message,
                "last_event_seq": job.last_event_seq,
            }
            high_water = job.last_event_seq
            replay = []
            cursor = after
            while cursor < high_water:
                events, _ = await service.list_events(task_id, after=cursor, limit=500)
                page = [event for event in events if event.seq <= high_water]
                if not page:
                    break
                replay.extend(page)
                cursor = page[-1].seq

        await websocket.send_json({"type": "snapshot", "data": snapshot})
        last_seq = after
        for event in replay:
            last_seq = event.seq
            await websocket.send_json(serialize_event_envelope(event))
        if snapshot["status"] in runtime.terminal_statuses:
            await websocket.send_json({"type": "done", "task_id": task_id, "seq": high_water})
            return

        while True:
            event = await subscription.get()
            seq = event.get("seq", 0)
            if seq <= max(high_water, last_seq):
                continue
            last_seq = seq
            await websocket.send_json(event)
            if event.get("data", {}).get("event_type") == "done":
                await websocket.send_json({"type": "done", "task_id": task_id, "seq": seq})
                break
    except WebSocketDisconnect:
        pass
    finally:
        runtime.unsubscribe(task_id, subscription)
