import pytest
from gateway.websocket_hub import ConnectionManager


def test_connection_count_starts_zero():
    manager = ConnectionManager()
    assert manager.connection_count == 0
