"""registration 路由行为测试。

routes:
  POST /register/outlook  → worker.process_manager.task_manager.submit(idx, proxy, config)
                            + worker.process_manager._fetch_proxy_from_manager()
                            + gateway.registration_helpers.resolve_registration_mode()
  GET  /tasks/{task_id}  → worker.process_manager.task_manager.get_status(task_id)

process_manager 中的 task_manager 是模块级单例；路由在函数体内懒导入，
所以 patch 目标是 worker.process_manager.task_manager（单例方法）
以及 worker.process_manager._fetch_proxy_from_manager（函数）。
"""

from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────
# POST /register/outlook
# ──────────────────────────────────────────────

def test_register_outlook_happy_single(client):
    """count=1，无 proxy → _fetch_proxy_from_manager → submit → task_ids 长度 1。"""
    with patch("worker.process_manager.task_manager") as mock_tm, \
         patch("worker.process_manager._fetch_proxy_from_manager", return_value="socks5://1.2.3.4:1080"):
        mock_tm.submit.return_value = "tid-001"

        r = client.post("/register/outlook", json={"count": 1, "config": {"headless": True}})

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["count"] == 1
    assert data["status"] == "running"
    assert data["task_ids"] == ["tid-001"]
    mock_tm.submit.assert_called_once()


def test_register_outlook_happy_multi(client):
    """count=3 → 调用 submit 三次 → 返回 3 个 task_id。"""
    task_ids = ["tid-a", "tid-b", "tid-c"]
    call_count = 0

    def fake_submit(**kwargs):
        nonlocal call_count
        tid = task_ids[call_count]
        call_count += 1
        return tid

    with patch("worker.process_manager.task_manager") as mock_tm, \
         patch("worker.process_manager._fetch_proxy_from_manager", return_value=""):
        mock_tm.submit.side_effect = fake_submit

        r = client.post("/register/outlook", json={"count": 3})

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["count"] == 3
    assert len(data["task_ids"]) == 3


def test_register_outlook_uses_provided_proxy(client):
    """body 中已提供 proxy → 不调用 _fetch_proxy_from_manager。"""
    with patch("worker.process_manager.task_manager") as mock_tm, \
         patch("worker.process_manager._fetch_proxy_from_manager") as mock_fetch:
        mock_tm.submit.return_value = "tid-proxy"

        r = client.post(
            "/register/outlook",
            json={"count": 1, "proxy": "socks5://user:pw@9.9.9.9:1080"},
        )

    assert r.status_code == 200
    mock_fetch.assert_not_called()
    # submit 被调用时 proxy 应该是传入的那个
    call_kwargs = mock_tm.submit.call_args[1]
    assert call_kwargs.get("proxy") == "socks5://user:pw@9.9.9.9:1080"


def test_register_outlook_rotates_sid_per_window(client):
    """count=2 并发：每个 submit 的 proxy 轮换不同 sid → 不同出口 IP
    (避免 PerimeterX 因同 IP 关联多个账号)。"""
    import re

    proxies_used = []

    def fake_submit(**kwargs):
        proxies_used.append(kwargs.get("proxy"))
        return f"tid-{len(proxies_used)}"

    base = "socks5://sb7f3017-region-Rand-sid-ORIG1234-t-5:pw@us.1024proxy.io:3000"
    with patch("worker.process_manager.task_manager") as mock_tm, \
         patch("worker.process_manager._fetch_proxy_from_manager", return_value=base):
        mock_tm.submit.side_effect = fake_submit
        r = client.post("/register/outlook", json={"count": 2})

    assert r.status_code == 200
    assert len(proxies_used) == 2
    sids = [re.search(r"-sid-([A-Za-z0-9]+)-t-", p).group(1) for p in proxies_used]
    assert sids[0] != sids[1]  # 两窗口 sid 不同
    assert all("us.1024proxy.io:3000" in p for p in proxies_used)
    assert all(p.startswith("socks5://sb7f3017-region-Rand-sid-") for p in proxies_used)


def test_register_outlook_mode_from_body(client):
    """body.mode 优先级最高，config 中传入的 mode 会被覆盖。"""
    with patch("worker.process_manager.task_manager") as mock_tm, \
         patch("worker.process_manager._fetch_proxy_from_manager", return_value=""):
        mock_tm.submit.return_value = "tid-mode"

        r = client.post(
            "/register/outlook",
            json={"count": 1, "mode": "hybrid", "config": {"mode": "browser"}},
        )

    assert r.status_code == 200
    call_kwargs = mock_tm.submit.call_args[1]
    # config["mode"] 应由 resolve_registration_mode 决定，应为 "hybrid"
    assert call_kwargs.get("config", {}).get("mode") == "hybrid"


def test_register_outlook_default_mode_browser(client):
    """不传 mode → 默认 'browser'。"""
    with patch("worker.process_manager.task_manager") as mock_tm, \
         patch("worker.process_manager._fetch_proxy_from_manager", return_value=""):
        mock_tm.submit.return_value = "tid-default-mode"

        r = client.post("/register/outlook", json={})

    assert r.status_code == 200
    call_kwargs = mock_tm.submit.call_args[1]
    assert call_kwargs.get("config", {}).get("mode") == "browser"


def test_register_outlook_empty_body(client):
    """空 body（合法 JSON）也应成功——路由有默认值。"""
    with patch("worker.process_manager.task_manager") as mock_tm, \
         patch("worker.process_manager._fetch_proxy_from_manager", return_value=""):
        mock_tm.submit.return_value = "tid-empty"
        r = client.post("/register/outlook", json={})

    assert r.status_code == 200
    assert r.json()["data"]["count"] == 1  # 默认 count=1


# ──────────────────────────────────────────────
# GET /tasks/{task_id}
# ──────────────────────────────────────────────

def test_get_task_status_running(client):
    """task_manager.get_status 返回 running 状态。"""
    fake_status = {"status": "running", "task_id": "tid-001", "elapsed": 10}

    with patch("worker.process_manager.task_manager") as mock_tm:
        mock_tm.get_status.return_value = fake_status
        r = client.get("/tasks/tid-001")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "running"
    assert data["task_id"] == "tid-001"
    mock_tm.get_status.assert_called_once_with("tid-001")


def test_get_task_status_completed(client):
    """task_manager.get_status 返回 completed 状态。"""
    fake_status = {"status": "completed", "task_id": "tid-002", "exitcode": 0, "elapsed": 45}

    with patch("worker.process_manager.task_manager") as mock_tm:
        mock_tm.get_status.return_value = fake_status
        r = client.get("/tasks/tid-002")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "completed"
    assert data["exitcode"] == 0


def test_get_task_status_unknown(client):
    """task_id 不存在 → get_status 返回 unknown。"""
    fake_status = {"status": "unknown", "task_id": "no-such-task"}

    with patch("worker.process_manager.task_manager") as mock_tm:
        mock_tm.get_status.return_value = fake_status
        r = client.get("/tasks/no-such-task")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "unknown"
