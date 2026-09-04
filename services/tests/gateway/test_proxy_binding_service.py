"""绑定抢占服务测试。用内存 SQLite 建真表，验证唯一约束真的拦得住。"""
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gateway.models import ProxyBinding, ProxyEntry
from gateway.proxy_binding_service import ProxyBindingService, build_proxy_url
from shared.base_model import BaseModel


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _add_proxy(session, host="1.2.3.4", status="active"):
    proxy = ProxyEntry(type="http", host=host, port=8080, username="u",
                       password="p", status=status)
    session.add(proxy)
    await session.flush()
    return proxy


async def test_claim_returns_url_and_creates_binding(session):
    proxy = await _add_proxy(session)
    claim = await ProxyBindingService(session).claim("task-1", "google")
    assert claim is not None
    assert claim.proxy_url == "http://u:p@1.2.3.4:8080"
    assert claim.proxy_id == proxy.id


async def test_second_claim_picks_a_different_proxy(session):
    await _add_proxy(session, host="1.1.1.1")
    await _add_proxy(session, host="2.2.2.2")
    svc = ProxyBindingService(session)
    first = await svc.claim("task-1", "google")
    second = await svc.claim("task-2", "google")
    assert first.proxy_id != second.proxy_id


async def test_claim_returns_none_when_pool_exhausted_today(session):
    await _add_proxy(session)
    svc = ProxyBindingService(session)
    assert await svc.claim("task-1", "google") is not None
    assert await svc.claim("task-2", "google") is None


async def test_inactive_proxies_are_not_candidates(session):
    await _add_proxy(session, status="inactive")
    assert await ProxyBindingService(session).claim("task-1", "google") is None


async def test_yesterday_binding_does_not_block_today(session):
    proxy = await _add_proxy(session)
    session.add(ProxyBinding(proxy_id=proxy.id, bound_date=date.today() - timedelta(days=1),
                             task_id="old", status="success"))
    await session.flush()
    assert await ProxyBindingService(session).claim("task-1", "google") is not None


async def test_claim_specific_conflicts_when_already_bound_today(session):
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    assert await svc.claim_specific(proxy.id, "task-1", "google") is not None
    assert await svc.claim_specific(proxy.id, "task-2", "google") is None


async def test_session_still_usable_after_conflict(session):
    """撞唯一约束后事务必须仍可用——savepoint 隔离生效的证明。"""
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim_specific(proxy.id, "task-1", "google")
    await svc.claim_specific(proxy.id, "task-2", "google")
    await _add_proxy(session, host="9.9.9.9")      # 冲突后还能继续写
    await session.flush()


async def test_mark_opened_then_finalize_keeps_binding(session):
    proxy = await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim("task-1", "google")
    await svc.mark_opened("task-1", "777", "a@gmail.com")
    await svc.finalize("task-1", success=True)
    summary = await svc.today_summary()
    assert summary[str(proxy.id)]["today_bound"] == 1
    assert summary[str(proxy.id)]["today_profile_name"] == "a@gmail.com"


async def test_finalize_releases_binding_that_never_opened(session):
    """窗口没建成 → 删记录还回当天配额。"""
    await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim("task-1", "google")
    await svc.finalize("task-1", success=False)
    assert await svc.claim("task-2", "google") is not None


async def test_finalize_keeps_opened_binding_on_failure(session):
    """窗口建成过就算占用，失败也不还。"""
    await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim("task-1", "google")
    await svc.mark_opened("task-1", "777", None)
    await svc.finalize("task-1", success=False)
    assert await svc.claim("task-2", "google") is None


async def test_today_summary_counts_total_and_today(session):
    proxy = await _add_proxy(session)
    session.add(ProxyBinding(proxy_id=proxy.id, bound_date=date.today() - timedelta(days=2),
                             task_id="old", status="success"))
    await session.flush()
    await ProxyBindingService(session).claim("task-1", "google")
    summary = await ProxyBindingService(session).today_summary()
    assert summary[str(proxy.id)]["total_bound"] == 2
    assert summary[str(proxy.id)]["today_bound"] == 1


def test_build_proxy_url_without_credentials():
    proxy = ProxyEntry(type="http", host="1.2.3.4", port=8080, username=None, password=None)
    assert build_proxy_url(proxy) == "http://1.2.3.4:8080"
