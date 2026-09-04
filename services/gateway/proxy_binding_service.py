"""代理当天绑定的抢占、回填与聚合。

唯一持有 proxy_bindings 事务逻辑的地方。抢占靠 UNIQUE(proxy_id, bound_date)
做硬保证，不用「先查后插」——并发下先查后插必然漏。
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models import ProxyBinding, ProxyEntry
from gateway.proxy_manager import DailyUniqueAllocator, LeastUsedAllocator

ACTIVE_STATUSES = ("active", "available")


def today_local() -> date:
    """本地自然日。注意 TimestampMixin 的时间戳是 UTC，两者不可混用。"""
    return datetime.now().date()


def build_proxy_url(proxy: ProxyEntry) -> str:
    """组装连接串。密码只在服务端出现，绝不返回浏览器。"""
    auth = f"{proxy.username}:{proxy.password}@" if proxy.username and proxy.password else ""
    return f"{proxy.type or 'socks5'}://{auth}{proxy.host}:{proxy.port}"


@dataclass(frozen=True)
class ProxyClaim:
    proxy_url: str
    binding_id: uuid.UUID
    proxy_id: uuid.UUID


class ProxyBindingService:
    def __init__(self, session: AsyncSession):
        self._session = session

    # ---------------- 查询 ----------------

    async def get_proxy(self, proxy_id) -> ProxyEntry | None:
        try:
            identifier = proxy_id if isinstance(proxy_id, uuid.UUID) else uuid.UUID(str(proxy_id))
        except ValueError:
            return None
        result = await self._session.execute(select(ProxyEntry).where(ProxyEntry.id == identifier))
        return result.scalar_one_or_none()

    async def _bound_today_ids(self) -> set[str]:
        result = await self._session.execute(
            select(ProxyBinding.proxy_id).where(ProxyBinding.bound_date == today_local())
        )
        return {str(pid) for pid in result.scalars().all()}

    async def _usage_counts(self) -> dict[str, int]:
        result = await self._session.execute(
            select(ProxyBinding.proxy_id, func.count(ProxyBinding.id)).group_by(ProxyBinding.proxy_id)
        )
        return {str(pid): int(count) for pid, count in result.all()}

    # ---------------- 抢占 ----------------

    async def _insert_binding(self, proxy: ProxyEntry, task_id: str, platform: str) -> ProxyClaim | None:
        """INSERT 一条 binding。撞唯一约束返回 None。

        必须用 begin_nested() 的 SAVEPOINT 包住：AsyncSession 撞 IntegrityError 后
        整个事务进入失败态，不隔离就会把同事务里待提交的 Job 一起拖垮。
        """
        binding = ProxyBinding(
            proxy_id=proxy.id, bound_date=today_local(), task_id=task_id,
            platform=platform, status="claimed",
        )
        try:
            async with self._session.begin_nested():
                self._session.add(binding)
        except IntegrityError:
            return None
        return ProxyClaim(proxy_url=build_proxy_url(proxy), binding_id=binding.id, proxy_id=proxy.id)

    async def claim(self, task_id: str, platform: str) -> ProxyClaim | None:
        """原子抢占一个今日未用的可用代理。池子见底返回 None。"""
        result = await self._session.execute(select(ProxyEntry))
        candidates = [p for p in result.scalars().all() if p.status in ACTIVE_STATUSES]
        by_id = {str(p.id): p for p in candidates}
        bound = await self._bound_today_ids()
        usage = await self._usage_counts()

        while True:
            allocator = DailyUniqueAllocator(LeastUsedAllocator(usage), bound)
            picked = allocator.select([{"id": str(p.id)} for p in candidates])
            if picked is None:
                return None
            proxy = by_id[picked["id"]]
            claim = await self._insert_binding(proxy, task_id, platform)
            if claim is not None:
                return claim
            bound.add(str(proxy.id))          # 被并发任务抢走，换下一个

    async def claim_specific(self, proxy_id, task_id: str, platform: str) -> ProxyClaim | None:
        """手动指定路径。该代理今日已绑返回 None（调用方转 409）。"""
        proxy = await self.get_proxy(proxy_id)
        if proxy is None:
            return None
        return await self._insert_binding(proxy, task_id, platform)

    # ---------------- 回填与收尾 ----------------

    async def mark_opened(self, task_id: str, profile_id, profile_name: str | None = None) -> None:
        await self._session.execute(
            update(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "claimed")
            .values(status="opened", profile_id=str(profile_id), profile_name=profile_name)
        )

    async def finalize(self, task_id: str, success: bool) -> None:
        """终态收尾。两条语句 WHERE 互斥，覆盖全部三种情形：
        成功 → opened 标 success，无 claimed 可删；
        失败但窗口建过 → opened 标 failed，仍占当天；
        失败且窗口没建成 → 无 opened 可标，claimed 被删，还回配额。
        """
        await self._session.execute(
            update(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "opened")
            .values(status="success" if success else "failed")
        )
        await self._session.execute(
            delete(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "claimed")
        )

    async def release_unopened(self, task_id: str) -> None:
        """崩溃恢复用：清掉从未建成窗口的占位。"""
        await self._session.execute(
            delete(ProxyBinding)
            .where(ProxyBinding.task_id == task_id, ProxyBinding.status == "claimed")
        )

    # ---------------- 聚合 ----------------

    async def today_summary(self) -> dict[str, dict]:
        """返回 {proxy_id: {total_bound, today_bound, today_profile_name}}。
        固定两条查询，不随代理数量增长。"""
        totals = await self._session.execute(
            select(ProxyBinding.proxy_id, func.count(ProxyBinding.id)).group_by(ProxyBinding.proxy_id)
        )
        summary = {
            str(pid): {"total_bound": int(count), "today_bound": 0, "today_profile_name": None}
            for pid, count in totals.all()
        }
        rows = await self._session.execute(
            select(ProxyBinding).where(ProxyBinding.bound_date == today_local())
        )
        for binding in rows.scalars().all():
            entry = summary.setdefault(
                str(binding.proxy_id),
                {"total_bound": 0, "today_bound": 0, "today_profile_name": None},
            )
            entry["today_bound"] = 1
            entry["today_profile_name"] = binding.profile_name
        return summary

    async def list_bindings(self, proxy_id, limit: int = 50, offset: int = 0) -> list[ProxyBinding]:
        proxy = await self.get_proxy(proxy_id)
        if proxy is None:
            return []
        result = await self._session.execute(
            select(ProxyBinding)
            .where(ProxyBinding.proxy_id == proxy.id)
            .order_by(ProxyBinding.bound_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def quota(self) -> dict[str, int]:
        total = await self._session.execute(
            select(func.count(ProxyEntry.id)).where(ProxyEntry.status.in_(ACTIVE_STATUSES))
        )
        total_count = int(total.scalar() or 0)
        used = len(await self._bound_today_ids())
        return {"total": total_count, "used_today": used,
                "available_today": max(total_count - used, 0)}
