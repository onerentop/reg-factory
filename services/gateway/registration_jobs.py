"""注册任务的持久化状态服务。"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models import RegistrationJob, TaskEvent


class RegistrationJobService:
    """SQLite 中任务状态投影及 append-only 事件流的唯一入口。"""

    _MAX_MESSAGE_LENGTH = 4_000

    def __init__(self, session: AsyncSession):
        self._session = session

    async def enqueue(self, task_id: str, platform: str) -> RegistrationJob:
        job = await self.get_by_task_id(task_id)
        if job is not None:
            return job
        job = RegistrationJob(
            task_id=task_id,
            platform=platform,
            status="queued",
            last_event_seq=0,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_by_task_id(self, task_id: str) -> RegistrationJob | None:
        result = await self._session.execute(
            select(RegistrationJob).where(RegistrationJob.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def append_event(
        self,
        task_id: str,
        *,
        platform: str,
        event_type: str,
        status: str | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
        message: str | None = None,
        level: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> TaskEvent:
        """原子追加事件，并在同一事务中维护任务状态投影。"""
        job = await self.enqueue(task_id, platform)
        job.last_event_seq += 1
        if status is not None:
            job.status = status
        if result is not None:
            job.result = result
        if error_message is not None:
            job.error_message = error_message[:1000]

        event = TaskEvent(
            task_id=task_id,
            seq=job.last_event_seq,
            event_type=event_type,
            status=status,
            level=level,
            message=message[:self._MAX_MESSAGE_LENGTH] if message else None,
            data=data,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_events(
        self, task_id: str, *, after: int = 0, limit: int = 100
    ) -> tuple[list[TaskEvent], bool]:
        """按稳定序号读取任务事件，供 REST 与 WebSocket 续传复用。"""
        bounded_limit = min(max(limit, 1), 500)
        result = await self._session.execute(
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id, TaskEvent.seq > max(after, 0))
            .order_by(TaskEvent.seq)
            .limit(bounded_limit + 1)
        )
        events = list(result.scalars().all())
        return events[:bounded_limit], len(events) > bounded_limit

    async def update(
        self,
        task_id: str,
        *,
        platform: str,
        status: str,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> RegistrationJob:
        """兼容旧调用；新事件路径应使用 append_event。"""
        job = await self.enqueue(task_id, platform)
        job.status = status
        if result is not None:
            job.result = result
        if error_message is not None:
            job.error_message = error_message[:1000]
        await self._session.flush()
        return job

    async def mark_unfinished_interrupted(self) -> int:
        """服务重启后标记未完成任务，后续不重放外部副作用。"""
        result = await self._session.execute(
            select(RegistrationJob).where(
                RegistrationJob.status.in_({"queued", "running", "starting"})
            )
        )
        jobs = list(result.scalars().all())
        for job in jobs:
            await self.append_event(
                job.task_id,
                platform=job.platform,
                event_type="interrupted",
                status="interrupted",
                error_message="本机服务已重启；请确认外部状态后手动重试",
            )
        return len(jobs)


def serialize_job(job: RegistrationJob) -> dict[str, Any]:
    return {
        "task_id": job.task_id,
        "platform": job.platform,
        "status": job.status,
        "result": job.result,
        "error": job.error_message,
        "last_event_seq": getattr(job, "last_event_seq", 0),
        "created_at": str(job.created_at) if job.created_at else None,
        "updated_at": str(job.updated_at) if job.updated_at else None,
    }



def serialize_event(event: TaskEvent) -> dict[str, Any]:
    """将持久化事件编码为 HTTP/WS 共用的无敏感账户数据。"""
    return {
        "task_id": event.task_id,
        "seq": event.seq,
        "event_type": event.event_type,
        "status": event.status,
        "level": event.level,
        "message": event.message,
        "data": event.data,
        "created_at": str(event.created_at) if event.created_at else None,
    }


def serialize_event_envelope(event: TaskEvent) -> dict[str, Any]:
    """为实时推送和回放构造同一层 WebSocket envelope。"""
    serialized = serialize_event(event)
    return {
        "type": "event",
        "task_id": serialized["task_id"],
        "seq": serialized["seq"],
        "data": serialized,
    }
