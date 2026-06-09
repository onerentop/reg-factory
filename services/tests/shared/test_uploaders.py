import pytest
from shared.uploaders.graph_token_extractor import GraphTokenExtractor
from shared.uploaders.chatgpt2api import ChatGpt2ApiUploader
from shared.uploaders.token_uploader import TokenUploader


def test_graph_token_extractor_init():
    extractor = GraphTokenExtractor()
    assert extractor._client_id is not None


def test_chatgpt2api_uploader_init():
    uploader = ChatGpt2ApiUploader(host="http://localhost:3000", api_key="test")
    assert uploader._host == "http://localhost:3000"


def test_token_uploader_add_target():
    uploader = TokenUploader()
    uploader.add_target("cpa", "http://cpa.example.com/api", {"bearer": "key123"})
    assert "cpa" in uploader._targets


def test_token_uploader_unknown_target():
    import asyncio
    uploader = TokenUploader()
    result = asyncio.get_event_loop().run_until_complete(
        uploader.upload("nonexistent", {"email": "test"})
    )
    assert result["success"] is False


def test_token_uploader_idempotent():
    uploader = TokenUploader()
    uploader._uploaded.add("cpa:test@test.com")
    import asyncio
    uploader.add_target("cpa", "http://example.com", {})
    result = asyncio.get_event_loop().run_until_complete(
        uploader.upload("cpa", {"email": "test@test.com"})
    )
    assert result["success"] is True
    assert result.get("skipped") is True
