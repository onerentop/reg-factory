import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Any
from dataclasses import dataclass, field


@dataclass
class LogRecord:
    service: str
    level: str
    message: str
    trace_id: str = ""
    account_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AsyncBatchLogHandler(logging.Handler):
    """异步批量日志处理器。生产者-消费者模式。

    收集日志到内存缓冲区，达到阈值或超时后批量写入。
    """

    def __init__(
        self,
        service_name: str,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ):
        super().__init__()
        self._service_name = service_name
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer: list[LogRecord] = []
        self._callbacks: list[Any] = []

    def add_flush_callback(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, record: logging.LogRecord) -> None:
        log_entry = LogRecord(
            service=self._service_name,
            level=record.levelname,
            message=self.format(record),
            trace_id=getattr(record, "trace_id", ""),
            account_id=getattr(record, "account_id", ""),
            extra=getattr(record, "extra_data", {}),
        )
        self._buffer.append(log_entry)
        if len(self._buffer) >= self._batch_size:
            self._flush_sync()

    def _flush_sync(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        for callback in self._callbacks:
            try:
                callback(batch)
            except Exception:
                pass

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    def flush(self) -> None:
        self._flush_sync()


class LogFormatter(logging.Formatter):
    """结构化 JSON 日志格式化器。"""

    def __init__(self, service_name: str):
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "service": self._service_name,
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", ""),
        }, ensure_ascii=False)


def setup_logger(service_name: str, level: int = logging.INFO) -> logging.Logger:
    """为微服务创建标准日志器。"""
    logger = logging.getLogger(service_name)
    logger.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(LogFormatter(service_name))
    logger.addHandler(console_handler)

    batch_handler = AsyncBatchLogHandler(service_name)
    logger.addHandler(batch_handler)

    return logger
