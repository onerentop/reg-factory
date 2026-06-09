"""stdout 日志捕获器。劫持 print() 输出，同时发布到 Redis Pub/Sub。"""

import sys
import json
import threading
from datetime import datetime, timezone


class LogCapture:
    """捕获 stdout 并发布到 Redis 频道，同时保留原始输出。"""

    def __init__(self, task_id: str, redis_url: str = "redis://localhost:6379/0"):
        self._task_id = task_id
        self._redis_url = redis_url
        self._original_stdout = sys.stdout
        self._redis = None
        self._channel = f"task:{task_id}:logs"
        self._lines: list[str] = []

    def start(self) -> "LogCapture":
        try:
            import redis
            self._redis = redis.from_url(self._redis_url)
            self._redis.ping()
        except Exception:
            self._redis = None
        sys.stdout = self
        return self

    def stop(self) -> list[str]:
        sys.stdout = self._original_stdout
        if self._redis:
            try:
                self._redis.publish(self._channel, json.dumps({
                    "type": "done", "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
                self._redis.close()
            except Exception:
                pass
        return self._lines

    def write(self, text: str) -> int:
        if self._original_stdout and hasattr(self._original_stdout, 'write'):
            try:
                self._original_stdout.write(text)
            except Exception:
                pass

        if text.strip():
            self._lines.append(text.strip())
            if self._redis:
                try:
                    self._redis.publish(self._channel, json.dumps({
                        "type": "log",
                        "message": text.strip(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                except Exception:
                    pass

        return len(text)

    def flush(self) -> None:
        if self._original_stdout and hasattr(self._original_stdout, 'flush'):
            try:
                self._original_stdout.flush()
            except Exception:
                pass

    @property
    def encoding(self):
        return getattr(self._original_stdout, 'encoding', 'utf-8')

    def reconfigure(self, **kwargs):
        pass

    @property
    def buffer(self):
        return getattr(self._original_stdout, 'buffer', None)
