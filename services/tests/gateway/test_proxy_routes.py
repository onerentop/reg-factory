"""proxy 路由行为测试。

proxy.py 直接用 session.execute(select(...)) 操作 ProxyEntry ORM。
get_session 是一个 async generator dep（yield session），
override 必须也是 async generator 函数（不能是 lambda 返回 async_generator 对象）。
"""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from gateway.deps import get_session
from gateway.main import app


# ──────────────────────────────────────────────
# FakeProxyEntry
# ──────────────────────────────────────────────

class FakeProxyEntry:
    def __init__(self, pid=None, **kw):
        self.id = uuid.UUID(pid) if pid else uuid.uuid4()
        self.type = kw.get("type", "socks5")
        self.host = kw.get("host", "1.2.3.4")
        self.port = kw.get("port", 1080)
        self.username = kw.get("username")
        self.password = kw.get("password")
        self.status = kw.get("status", "active")
        self.region = kw.get("region")
        self.created_at = None


_MISSING = object()  # 哨兵，区分"未传"和显式传 None


# ──────────────────────────────────────────────
# FakeSession factory
# ──────────────────────────────────────────────

def make_fake_session(scalars_all=None, scalar_one_or_none=_MISSING):
    """构造 FakeSession，execute 返回的 FakeResult 行为由参数控制。"""
    # 捕获参数到闭包
    _scalars_all = scalars_all
    _scalar = scalar_one_or_none

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return _scalars_all if _scalars_all is not None else []

        def scalar_one_or_none(self):
            # _MISSING 表示未传入，默认 None
            return None if _scalar is _MISSING else _scalar

    class FakeSession:
        async def execute(self, stmt):
            return FakeResult()

        def add(self, obj):
            pass

        async def flush(self):
            pass

        async def refresh(self, obj):
            if not hasattr(obj, 'id') or obj.id is None:
                obj.id = uuid.uuid4()

        async def delete(self, obj):
            pass

    return FakeSession()


def _session_override(session):
    """返回一个 async generator 函数（可被 FastAPI DI 正确调用）。"""
    async def _override():
        yield session
    return _override


# ──────────────────────────────────────────────
# GET /proxy
# ──────────────────────────────────────────────

def test_list_proxies_empty(client):
    session = make_fake_session(scalars_all=[])
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.get("/proxy")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_list_proxies_with_items(client):
    entry = FakeProxyEntry()
    session = make_fake_session(scalars_all=[entry])
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.get("/proxy")
    assert r.status_code == 200
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["host"] == entry.host
    assert items[0]["port"] == entry.port
    assert "id" in items[0]
    assert "password" not in items[0]
    assert items[0]["has_password"] is False


def test_list_proxies_hides_password_when_set(client):
    """密码不能以明文出现在响应里，但 has_password 要如实反映它已设置。"""
    entry = FakeProxyEntry(password="secret")
    session = make_fake_session(scalars_all=[entry])
    app.dependency_overrides[get_session] = _session_override(session)
    resp = client.get("/proxy")
    assert resp.status_code == 200
    assert "secret" not in resp.text
    item = resp.json()["data"][0]
    assert "password" not in item
    assert item["has_password"] is True


def test_list_proxies_has_no_binding_fields(client):
    entry = FakeProxyEntry()
    session = make_fake_session(scalars_all=[entry])
    app.dependency_overrides[get_session] = _session_override(session)
    resp = client.get("/proxy")
    assert resp.status_code == 200
    for row in resp.json()["data"]:
        assert "today_bound" not in row
        assert "available_today" not in row
        assert {"id", "host", "port", "status"} <= set(row)


# ──────────────────────────────────────────────
# POST /proxy
# ──────────────────────────────────────────────

def test_add_proxy_happy(client):
    pid = str(uuid.uuid4())
    entry = FakeProxyEntry(pid=pid)

    class _Session:
        async def execute(self, stmt):
            return None
        def add(self, obj):
            obj.id = uuid.UUID(pid)
        async def flush(self):
            pass
        async def refresh(self, obj):
            obj.id = uuid.UUID(pid)
        async def delete(self, obj):
            pass

    app.dependency_overrides[get_session] = _session_override(_Session())

    r = client.post("/proxy", json={"host": "5.6.7.8", "port": 3128, "type": "http"})

    assert r.status_code == 200
    assert "id" in r.json()["data"]


def test_add_proxy_missing_port_is_rejected(client):
    """ProxyWrite 在访问数据库前拒绝缺失的必填端口。"""
    class _Session:
        async def execute(self, stmt): return None
        def add(self, obj): obj.id = uuid.uuid4()
        async def flush(self): pass
        async def refresh(self, obj): pass
        async def delete(self, obj): pass

    app.dependency_overrides[get_session] = _session_override(_Session())
    r = client.post("/proxy", json={"host": "x.x.x.x"})  # 缺 port
    assert r.status_code == 422


# ──────────────────────────────────────────────
# PUT /proxy/{id}
# ──────────────────────────────────────────────

def test_update_proxy_happy(client):
    pid = str(uuid.uuid4())
    entry = FakeProxyEntry(pid=pid, host="1.1.1.1", port=1080)
    session = make_fake_session(scalar_one_or_none=entry)
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.put(f"/proxy/{pid}", json={"host": "2.2.2.2"})
    assert r.status_code == 200
    assert r.json()["data"]["id"] == pid


def test_update_proxy_not_found(client):
    pid = str(uuid.uuid4())
    session = make_fake_session(scalar_one_or_none=None)
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.put(f"/proxy/{pid}", json={"host": "2.2.2.2"})
    assert r.status_code == 404


def test_update_proxy_invalid_uuid(client):
    """非 UUID proxy_id → uuid.UUID() 抛 ValueError。
    TestClient 默认重新抛出服务器异常；用 raise_server_exceptions=False 验证 500。"""
    session = make_fake_session(scalar_one_or_none=None)
    app.dependency_overrides[get_session] = _session_override(session)
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    r = no_raise_client.put("/proxy/not-a-uuid", json={"host": "2.2.2.2"})
    assert r.status_code == 500


# ──────────────────────────────────────────────
# DELETE /proxy/{id}
# ──────────────────────────────────────────────

def test_delete_proxy_happy(client):
    pid = str(uuid.uuid4())
    entry = FakeProxyEntry(pid=pid)
    session = make_fake_session(scalar_one_or_none=entry)
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.delete(f"/proxy/{pid}")
    assert r.status_code == 200
    assert r.json()["message"] == "Deleted"


def test_delete_proxy_not_found(client):
    pid = str(uuid.uuid4())
    session = make_fake_session(scalar_one_or_none=None)
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.delete(f"/proxy/{pid}")
    assert r.status_code == 404


# ──────────────────────────────────────────────
# POST /proxy/{id}/test
# ──────────────────────────────────────────────

def test_test_proxy_happy_available(client):
    pid = str(uuid.uuid4())
    entry = FakeProxyEntry(pid=pid, host="1.2.3.4", port=1080, type="socks5")
    session = make_fake_session(scalar_one_or_none=entry)
    app.dependency_overrides[get_session] = _session_override(session)

    with patch("gateway.proxy_manager.check_proxy_health", new=AsyncMock(return_value="available")), \
         patch("gateway.proxy_manager.detect_proxy_ip", new=AsyncMock(return_value={"ip": "1.2.3.4", "region": "US LA"})):
        r = client.post(f"/proxy/{pid}/test")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["result"] == "available"
    assert data["ip"] == "1.2.3.4"


def test_test_proxy_unavailable(client):
    pid = str(uuid.uuid4())
    entry = FakeProxyEntry(pid=pid)
    session = make_fake_session(scalar_one_or_none=entry)
    app.dependency_overrides[get_session] = _session_override(session)

    with patch("gateway.proxy_manager.check_proxy_health", new=AsyncMock(return_value="unavailable")):
        r = client.post(f"/proxy/{pid}/test")

    assert r.status_code == 200
    assert r.json()["data"]["result"] == "unavailable"
    assert r.json()["data"]["ip"] == ""


def test_test_proxy_slow(client):
    """slow 也触发 detect_proxy_ip。"""
    pid = str(uuid.uuid4())
    entry = FakeProxyEntry(pid=pid)
    session = make_fake_session(scalar_one_or_none=entry)
    app.dependency_overrides[get_session] = _session_override(session)

    with patch("gateway.proxy_manager.check_proxy_health", new=AsyncMock(return_value="slow")), \
         patch("gateway.proxy_manager.detect_proxy_ip", new=AsyncMock(return_value={"ip": "9.9.9.9", "region": "JP Tokyo"})):
        r = client.post(f"/proxy/{pid}/test")

    assert r.status_code == 200
    assert r.json()["data"]["result"] == "slow"
    assert r.json()["data"]["ip"] == "9.9.9.9"


def test_test_proxy_not_found(client):
    pid = str(uuid.uuid4())
    session = make_fake_session(scalar_one_or_none=None)
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.post(f"/proxy/{pid}/test")
    assert r.status_code == 404


# ──────────────────────────────────────────────
# PUT /proxy/{id}/status
# ──────────────────────────────────────────────

def test_update_proxy_status_happy(client):
    pid = str(uuid.uuid4())
    entry = FakeProxyEntry(pid=pid, status="active")
    session = make_fake_session(scalar_one_or_none=entry)
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.put(f"/proxy/{pid}/status", json={"status": "disabled"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == pid
    assert data["status"] == "disabled"


def test_update_proxy_status_not_found(client):
    pid = str(uuid.uuid4())
    session = make_fake_session(scalar_one_or_none=None)
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.put(f"/proxy/{pid}/status", json={"status": "disabled"})
    assert r.status_code == 404


# ──────────────────────────────────────────────
# POST /proxy/import
# ──────────────────────────────────────────────

def _import_session(existing=None):
    """导入路由用的 fake session：execute 返回库内已有代理，add 收集新建项。"""
    added = []
    rows = existing or []

    class _Session:
        async def execute(self, stmt):
            class R:
                def scalars(self_inner): return self_inner
                def all(self_inner): return rows
            return R()
        def add(self, obj):
            obj.id = uuid.uuid4()
            added.append(obj)
        async def flush(self): pass
        async def refresh(self, obj): pass
        async def delete(self, obj): pass

    return _Session(), added


def test_import_proxies_creates_entries(client):
    session, added = _import_session()
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.post("/proxy/import", json={
        "text": "45.61.125.104:6115:proxyuser:proxypass\n136.0.186.187:6548:proxyuser:proxypass",
        "type": "http",
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["imported"] == 2 and data["duplicates"] == 0 and data["invalid"] == []
    assert added[0].type == "http" and added[0].port == 6115
    assert added[0].username == "proxyuser" and added[0].password == "proxypass"


def test_imported_proxies_are_active_and_claimable(client):
    """导入必须显式设 status='active'。默认值 'unknown' 不可被抢占，
    漏设会让整池静默失效——这条测试是那道防线。"""
    session, added = _import_session()
    app.dependency_overrides[get_session] = _session_override(session)
    client.post("/proxy/import", json={"text": "1.2.3.4:8080:u:p", "type": "http"})
    from gateway.proxy_binding_service import ACTIVE_STATUSES
    assert added[0].status in ACTIVE_STATUSES


def test_import_reports_invalid_lines(client):
    session, _ = _import_session()
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.post("/proxy/import", json={"text": "1.2.3.4:8080\ngarbage", "type": "http"})
    data = r.json()["data"]
    assert data["imported"] == 1
    assert data["invalid"][0]["line_no"] == 2
    assert data["invalid"][0]["raw"] == "garbage"
    assert data["invalid"][0]["reason"]


def test_import_skips_existing_host_port(client):
    existing = FakeProxyEntry(host="1.2.3.4", port=8080)
    session, added = _import_session([existing])
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.post("/proxy/import", json={"text": "1.2.3.4:8080", "type": "http"})
    data = r.json()["data"]
    assert data["imported"] == 0 and data["duplicates"] == 1
    assert added == []


def test_import_deduplicates_within_the_same_paste(client):
    """同一次粘贴里的重复行也只入库一条。"""
    session, added = _import_session()
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.post("/proxy/import", json={"text": "1.2.3.4:8080\n1.2.3.4:8080", "type": "http"})
    data = r.json()["data"]
    assert data["imported"] == 1 and data["duplicates"] == 1
    assert len(added) == 1


def test_import_rejects_empty_text(client):
    session, _ = _import_session()
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.post("/proxy/import", json={"text": "", "type": "http"})
    assert r.status_code == 422


def test_import_rejects_bad_type(client):
    session, _ = _import_session()
    app.dependency_overrides[get_session] = _session_override(session)
    r = client.post("/proxy/import", json={"text": "1.2.3.4:8080", "type": "ftp"})
    assert r.status_code == 422


