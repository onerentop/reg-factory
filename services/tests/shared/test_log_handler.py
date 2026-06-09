import logging
from shared.log_handler import AsyncBatchLogHandler, LogFormatter, setup_logger, LogRecord


def test_batch_handler_buffers():
    handler = AsyncBatchLogHandler(service_name="test", batch_size=5)
    record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
    handler.emit(record)
    assert handler.buffer_size == 1


def test_batch_handler_flushes_at_threshold():
    flushed = []
    handler = AsyncBatchLogHandler(service_name="test", batch_size=3)
    handler.add_flush_callback(lambda batch: flushed.extend(batch))
    for i in range(3):
        record = logging.LogRecord("test", logging.INFO, "", 0, f"msg{i}", (), None)
        handler.emit(record)
    assert handler.buffer_size == 0
    assert len(flushed) == 3


def test_log_formatter():
    formatter = LogFormatter(service_name="sms")
    record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
    output = formatter.format(record)
    assert "sms" in output
    assert "hello" in output


def test_setup_logger():
    logger = setup_logger("test_service")
    assert logger.name == "test_service"
    assert len(logger.handlers) >= 2
