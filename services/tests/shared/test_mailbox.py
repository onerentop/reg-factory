import pytest
from shared.mailbox.graph_client import GraphClient
from shared.mailbox.code_extractor import CodeExtractor


def test_graph_client_init():
    client = GraphClient()
    assert client._client_id is not None


def test_graph_client_custom_id():
    client = GraphClient(client_id="custom-id")
    assert client._client_id == "custom-id"


def test_code_extractor_init():
    extractor = CodeExtractor()
    assert extractor._graph is not None


def test_match_message_no_hints():
    assert CodeExtractor._match_message({}, "", "") is True


def test_match_message_sender():
    msg = {"from": {"emailAddress": {"address": "noreply@example.com"}}, "subject": "Test"}
    assert CodeExtractor._match_message(msg, "noreply", "") is True
    assert CodeExtractor._match_message(msg, "other", "") is False


def test_match_message_subject():
    msg = {"from": {"emailAddress": {"address": "a@b.com"}}, "subject": "Your verification code"}
    assert CodeExtractor._match_message(msg, "", "verification") is True
    assert CodeExtractor._match_message(msg, "", "password reset") is False
