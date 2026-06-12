import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gateway.websocket_hub import ws_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


@router.websocket("/ws/task/{task_id}/logs")
async def task_logs_websocket(websocket: WebSocket, task_id: str):
    """实时推送任务日志到前端。订阅 Redis Pub/Sub 频道 task:{task_id}:logs。"""
    await websocket.accept()
    import redis.asyncio as aioredis
    import json as _json
    try:
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        pubsub = r.pubsub()
        channel = f"task:{task_id}:logs"
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                await websocket.send_text(data)
                parsed = _json.loads(data)
                if parsed.get("type") == "done":
                    break
        await pubsub.unsubscribe(channel)
        await r.aclose()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(_json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
