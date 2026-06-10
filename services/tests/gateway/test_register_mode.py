import asyncio
from gateway.main import trigger_outlook_registration
from worker import process_manager


def _run(coro):
    return asyncio.run(coro)


def test_mode_passed_into_config(monkeypatch):
    captured = []

    def fake_submit(idx=0, proxy="", config=None):
        captured.append(config)
        return f"task-{idx}"

    monkeypatch.setattr(process_manager.task_manager, "submit", fake_submit)
    monkeypatch.setattr(process_manager, "_fetch_proxy_from_manager", lambda: "fake-proxy")

    _run(trigger_outlook_registration({"count": 2, "proxy": "p", "mode": "hybrid"}))
    assert len(captured) == 2
    assert all(c.get("mode") == "hybrid" for c in captured)


def test_mode_defaults_to_browser(monkeypatch):
    captured = []

    def fake_submit(idx=0, proxy="", config=None):
        captured.append(config)
        return f"task-{idx}"

    monkeypatch.setattr(process_manager.task_manager, "submit", fake_submit)
    monkeypatch.setattr(process_manager, "_fetch_proxy_from_manager", lambda: "fake-proxy")

    _run(trigger_outlook_registration({"count": 1, "proxy": "p"}))
    assert captured[0].get("mode") == "browser"


def test_mode_from_config_when_no_toplevel(monkeypatch):
    captured = []

    def fake_submit(idx=0, proxy="", config=None):
        captured.append(config)
        return f"task-{idx}"

    monkeypatch.setattr(process_manager.task_manager, "submit", fake_submit)
    monkeypatch.setattr(process_manager, "_fetch_proxy_from_manager", lambda: "fake-proxy")

    _run(trigger_outlook_registration({"count": 1, "proxy": "p", "config": {"mode": "protocol"}}))
    assert captured[0].get("mode") == "protocol"
