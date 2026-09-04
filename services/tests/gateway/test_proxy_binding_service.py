"""绑定抢占服务测试。用真实文件 SQLite 建真表，验证唯一约束真的拦得住。

引擎经 DatabaseManager 创建（而非裸 create_async_engine），
这样才会挂上 shared/database.py 里那对 isolation_level=None + 显式 BEGIN 的监听器，
测试才真正跑在和生产一致的事务语义下——见 test_claim_rolled_back_leaves_no_binding。
"""
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from gateway import proxy_binding_service as pbs
from gateway.models import ProxyBinding, ProxyEntry
from gateway.proxy_binding_service import ProxyBindingService, build_proxy_url, today_local
from shared.base_model import BaseModel
from shared.database import DatabaseManager


class _FakeClock:
    """本地 2026-09-05 01:00 / UTC 2026-09-04 17:00——两个时钟的自然日不同。

    UTC+8 的机器上，本地 00:00-07:59 这个窗口里两者才会分家。
    真实时钟几乎永远撞不上它，所以只能把时钟钉死来测。
    """

    @staticmethod
    def now(tz=None):
        if tz is not None:                       # datetime.now(timezone.utc) 写法
            return datetime(2026, 9, 4, 17, 0, tzinfo=tz)
        return datetime(2026, 9, 5, 1, 0)

    @staticmethod
    def utcnow():                                # datetime.utcnow() 写法
        return datetime(2026, 9, 4, 17, 0)


@pytest_asyncio.fixture
async def session(tmp_path):
    """经 DatabaseManager 建引擎——覆盖生产事务语义，而不是裸 create_async_engine。

    落文件而非 :memory:：内存库连接语义和文件库有细节差异，durability 恰恰是本文件
    要验证的东西，落文件才和生产（真实 regfactory.db）同构，与
    tests/shared/test_database_transactions.py 的选择保持一致。

    用 manager._session_factory() 而不是 manager.get_session()：get_session() 是
    「成功自动 commit、异常自动 rollback」的请求级包装，但这里的测试要在同一个
    session 里反复 flush() 并跨多次调用读回未提交的状态（部分测试还会在同一个
    session 上再建一个 ProxyBindingService），commit-on-exit 的语义并不匹配；
    _session_factory 给的是和旧 fixture 完全对等的裸 session，只是引擎换成了
    DatabaseManager 配置过的那个。
    """
    manager = DatabaseManager(url=f"sqlite+aiosqlite:///{tmp_path / 'proxy_binding.db'}")
    async with manager.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    assert manager._session_factory is not None
    async with manager._session_factory() as s:
        yield s
    await manager.close()


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


async def test_claim_rolled_back_leaves_no_binding(session):
    """claim() 的写入落在 begin_nested() 的 SAVEPOINT 里，外层 session.rollback()
    必须真能撤销它——这正是 cfc59e8 修的坑：sqlite 驱动不接管事务的话，
    SAVEPOINT 一 RELEASE 就直接落盘，rollback() 形同虚设，无主 binding 永久占着
    当天配额。先 commit 代理本身，只把 claim() 这次写留在待回滚事务里，
    这样断言只盯住 SAVEPOINT 语义，不和外层 flush 的持久性混在一起。"""
    await _add_proxy(session)
    await session.commit()
    claim = await ProxyBindingService(session).claim("task-1", "google")
    assert claim is not None
    await session.rollback()
    rows = (await session.execute(select(ProxyBinding))).scalars().all()
    assert rows == []


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


async def test_mark_opened_with_none_profile_id_stays_null(session):
    """profile_id=None 必须落成 SQL NULL，不能是 4 字符的字符串 "None"。"""
    await _add_proxy(session)
    svc = ProxyBindingService(session)
    await svc.claim("task-1", "google")
    await svc.mark_opened("task-1", None)
    session.expire_all()                                   # 强制回库读，绕开身份映射
    binding = (await session.execute(select(ProxyBinding))).scalar_one()
    assert binding.status == "opened"
    assert binding.profile_id is None
    assert binding.profile_id != "None"


async def test_default_status_proxy_is_not_claimable(session):
    """ProxyEntry.status 默认是 'unknown'，不可被抢占。
    导入路径若忘记显式设 status='active'，整池会静默不可用——此测试是那道防线。"""
    proxy = ProxyEntry(type="http", host="1.2.3.4", port=8080, username="u", password="p")
    session.add(proxy)
    await session.flush()
    assert proxy.status == "unknown"
    assert await ProxyBindingService(session).claim("task-1", "google") is None


async def test_today_summary_counts_total_and_today(session):
    proxy = await _add_proxy(session)
    session.add(ProxyBinding(proxy_id=proxy.id, bound_date=date.today() - timedelta(days=2),
                             task_id="old", status="success"))
    await session.flush()
    await ProxyBindingService(session).claim("task-1", "google")
    summary = await ProxyBindingService(session).today_summary()
    assert summary[str(proxy.id)]["total_bound"] == 2
    assert summary[str(proxy.id)]["today_bound"] == 1


async def test_claim_specific_rejects_inactive_proxy(session):
    """手动路径必须和 claim() 用同一道状态闸门，否则死代理照样能被绑上窗口。"""
    proxy = await _add_proxy(session, status="inactive")
    assert await ProxyBindingService(session).claim_specific(proxy.id, "task-1", "google") is None


async def test_list_bindings_returns_newest_first(session):
    proxy = await _add_proxy(session)
    for offset, task in [(2, "old"), (1, "mid")]:
        session.add(ProxyBinding(proxy_id=proxy.id, bound_date=date.today() - timedelta(days=offset),
                                 task_id=task, status="success"))
    await session.flush()
    svc = ProxyBindingService(session)
    await svc.claim("task-now", "google")
    bindings = await svc.list_bindings(proxy.id)
    assert [b.task_id for b in bindings] == ["task-now", "mid", "old"]


async def test_quota_reports_pool_usage(session):
    await _add_proxy(session, host="1.1.1.1")
    await _add_proxy(session, host="2.2.2.2")
    await _add_proxy(session, host="3.3.3.3", status="inactive")   # 不计入总额
    svc = ProxyBindingService(session)
    assert await svc.quota() == {"total": 2, "used_today": 0, "available_today": 2}
    await svc.claim("task-1", "google")
    assert await svc.quota() == {"total": 2, "used_today": 1, "available_today": 1}


def test_today_local_tracks_local_clock_not_utc(monkeypatch):
    """钉死设计决策：自然日取本地时钟。实现改成 UTC 必须红。"""
    monkeypatch.setattr(pbs, "datetime", _FakeClock)
    assert today_local() == date(2026, 9, 5)          # 若取 UTC 则是 09-04


async def test_bound_date_uses_local_date_when_utc_disagrees(session, monkeypatch):
    """落库的 bound_date 本身也必须是本地自然日，不只是 today_local() 的返回值。"""
    await _add_proxy(session)
    monkeypatch.setattr(pbs, "datetime", _FakeClock)
    await ProxyBindingService(session).claim("task-1", "google")
    binding = (await session.execute(select(ProxyBinding))).scalar_one()
    assert binding.bound_date == date(2026, 9, 5)


def test_build_proxy_url_without_credentials():
    proxy = ProxyEntry(type="http", host="1.2.3.4", port=8080, username=None, password=None)
    assert build_proxy_url(proxy) == "http://1.2.3.4:8080"
