import json
import asyncio
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket 连接管理器。观察者模式——维护订阅者列表，广播事件。"""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def broadcast(self, event_type: str, data: dict) -> None:
        message = json.dumps({"type": event_type, "data": data})
        async with self._lock:
            stale = []
            for ws in self._connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self._connections.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


ws_manager = ConnectionManager()
