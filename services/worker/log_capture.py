"""子进程 stdout 日志捕获器，通过本机 IPC 发送结构化事件。"""

import re
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

_SECRET_PATTERN = re.compile(
    r"(?i)(authorization|cookie|password|refresh_token|access_token|proxy_password)"
    r"\s*[:=]\s*[^\s,;]+"
)


def redact_sensitive_text(text: str) -> str:
    """避免任务日志把密钥、Cookie 或代理认证信息回传给 API/前端。"""
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=***", text)


class LogCapture:
    """捕获 stdout，并通过传入的事件回调把日志交给 API 父进程。"""

    def __init__(self, task_id: str, emit: Callable[[dict[str, Any]], None]):
        self._task_id = task_id
        self._emit = emit
        self._original_stdout = sys.stdout
        self._sequence = 0

    def start(self) -> "LogCapture":
        sys.stdout = self
        return self

    def stop(self) -> None:
        sys.stdout = self._original_stdout

    def write(self, text: str) -> int:
        if self._original_stdout and hasattr(self._original_stdout, "write"):
            try:
                self._original_stdout.write(text)
            except Exception:
                pass

        message = text.strip()
        if message:
            self._sequence += 1
            self._emit(
                {
                    "type": "log",
                    "task_id": self._task_id,
                    "sequence": self._sequence,
                    "message": redact_sensitive_text(message),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        return len(text)

    def flush(self) -> None:
        if self._original_stdout and hasattr(self._original_stdout, "flush"):
            try:
                self._original_stdout.flush()
            except Exception:
                pass

    @property
    def encoding(self):
        return getattr(self._original_stdout, "encoding", "utf-8")

    def reconfigure(self, **_kwargs):
        return None

    @property
    def buffer(self):
        return getattr(self._original_stdout, "buffer", None)
