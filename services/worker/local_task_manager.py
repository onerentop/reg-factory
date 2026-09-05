"""无 Redis/Celery 的本机受控子进程任务管理器。"""

import asyncio
import multiprocessing
import queue
import time
import traceback
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from worker.log_capture import LogCapture


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "interrupted"})


def _emit(queue_: Any, event: dict[str, Any]) -> None:
    """子进程绝不写 SQLite；只把结构化事件交给 API 父进程。"""
    queue_.put(event)


def _registration_process(
    event_queue: Any,
    task_id: str,
    platform: str,
    idx: int,
    proxy: str,
    config: dict[str, Any],
) -> None:
    """可 pickle 的 Windows spawn 子进程入口。"""
    def emit(event: dict[str, Any]) -> None:
        _emit(event_queue, event)

    capture = LogCapture(task_id, emit).start()
    try:
        from worker.tasks.registration import execute_registration

        result, account = asyncio.run(
            execute_registration(
                task_id,
                platform,
                idx=idx,
                proxy=proxy,
                config=config,
                emit=emit,
            )
        )
        emit({"type": "result", "task_id": task_id, "data": result, "account": account})
    except Exception as error:
        emit(
            {
                "type": "failed",
                "task_id": task_id,
                "error": str(error),
                "traceback": traceback.format_exc(limit=8),
            }
        )
    finally:
        capture.stop()
        emit({"type": "done", "task_id": task_id})



def _callable_process(
    event_queue: Any,
    task_id: str,
    handler: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """工具和编排任务的受控子进程入口。"""
    capture = LogCapture(task_id, lambda event: _emit(event_queue, event)).start()
    try:
        module_name, function_name = handler.rsplit(":", 1)
        module = __import__(module_name, fromlist=[function_name])
        result = getattr(module, function_name)(*args, **kwargs)
        _emit(
            event_queue,
            {"type": "result", "task_id": task_id, "data": result, "status": "succeeded"},
        )
    except Exception as error:
        _emit(event_queue, {"type": "failed", "task_id": task_id, "error": str(error)})
    finally:
        capture.stop()
        _emit(event_queue, {"type": "done", "task_id": task_id})


class LocalProcessTaskManager:
    """单进程 FastAPI 所属的有界本机浏览器任务调度器。"""

    terminal_statuses = TERMINAL_STATUSES

    def __init__(self, max_concurrency: int = 1):
        self._context = multiprocessing.get_context("spawn")
        self._event_queue = self._context.Queue()
        self._max_concurrency = max_concurrency
        self._pending: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._processes: dict[str, multiprocessing.Process] = {}
        self._clean_exit_since: dict[str, float] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._drain_task: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self) -> None:
        self._closed = False
        self._drain_task = asyncio.create_task(self._drain_events(), name="local-task-events")

    async def stop(self) -> None:
        """终止未完成的本机任务，并把其持久化状态明确标为中断。"""
        self._closed = True
        active_jobs = [
            (task_id, process, await self.get_job(task_id))
            for task_id, process in self._processes.items()
        ]
        pending_jobs: list[dict[str, Any]] = []
        while not self._pending.empty():
            pending_jobs.append(self._pending.get_nowait())

        for _, process, _ in active_jobs:
            if process.is_alive():
                process.terminate()
        for _, process, _ in active_jobs:
            process.join(timeout=2)
        self._processes.clear()

        if self._drain_task is not None:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None

        for task_id, _, job in active_jobs:
            if job is None or job["status"] in TERMINAL_STATUSES:
                continue
            persisted = await self._persist_status(
                task_id,
                job["platform"],
                "interrupted",
                event_type="interrupted",
                error="本机服务正在关闭；任务已中断",
            )
            await self._broadcast(task_id, persisted)
        for job in pending_jobs:
            persisted = await self._persist_status(
                job["task_id"],
                job["platform"],
                "interrupted",
                event_type="interrupted",
                error="本机服务正在关闭；任务未启动",
            )
            await self._broadcast(job["task_id"], persisted)

        self._event_queue.close()

    async def submit_registration(
        self,
        task_id: str,
        *,
        platform: str,
        idx: int,
        proxy: str,
        config: dict[str, Any],
    ) -> None:
        if self._closed:
            raise RuntimeError("本机任务管理器正在关闭")
        await self._pending.put(
            {
                "task_id": task_id,
                "platform": platform,
                "idx": idx,
                "proxy": proxy,
                "config": config,
            }
        )
        await self._start_pending()

    async def submit_callable(
        self,
        task_id: str,
        *,
        platform: str,
        handler: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """提交工具/编排任务；handler 是模块级函数路径，适配 Windows spawn。"""
        if self._closed:
            raise RuntimeError("本机任务管理器正在关闭")
        await self._pending.put(
            {
                "task_id": task_id,
                "platform": platform,
                "handler": handler,
                "args": args,
                "kwargs": kwargs or {},
            }
        )
        await self._start_pending()

    def subscribe(self, task_id: str) -> asyncio.Queue[dict[str, Any]]:
        subscription: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers[task_id].add(subscription)
        return subscription

    def unsubscribe(self, task_id: str, subscription: asyncio.Queue[dict[str, Any]]) -> None:
        subscriptions = self._subscribers.get(task_id)
        if subscriptions is None:
            return
        subscriptions.discard(subscription)
        if not subscriptions:
            self._subscribers.pop(task_id, None)

    async def get_job(self, task_id: str) -> dict[str, Any] | None:
        from app.core.dependencies import db
        from gateway.registration_jobs import RegistrationJobService, serialize_job

        async with db.get_session() as session:
            job = await RegistrationJobService(session).get_by_task_id(task_id)
            return serialize_job(job) if job is not None else None

    async def mark_unfinished_interrupted(self) -> int:
        from app.core.dependencies import db
        from gateway.registration_jobs import RegistrationJobService

        async with db.get_session() as session:
            return await RegistrationJobService(session).mark_unfinished_interrupted()

    async def _start_pending(self) -> None:
        while len(self._processes) < self._max_concurrency and not self._pending.empty():
            job = self._pending.get_nowait()
            if "handler" in job:
                process = self._context.Process(
                    target=_callable_process,
                    kwargs={
                        "event_queue": self._event_queue,
                        "task_id": job["task_id"],
                        "handler": job["handler"],
                        "args": job["args"],
                        "kwargs": job["kwargs"],
                    },
                    daemon=False,
                )
            else:
                process = self._context.Process(
                    target=_registration_process,
                    kwargs={"event_queue": self._event_queue, **job},
                    daemon=False,
                )
            process.start()
            self._processes[job["task_id"]] = process
            persisted = await self._persist_status(
                job["task_id"], job["platform"], "starting", event_type="status"
            )
            await self._broadcast(job["task_id"], persisted)

    async def _drain_events(self) -> None:
        while True:
            try:
                event = await asyncio.to_thread(self._event_queue.get, True, 0.25)
            except queue.Empty:
                await self._reap_processes()
                continue
            await self._handle_event(event)

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """将 IPC 事件先提交到 SQLite，再以携带 seq 的 envelope 广播。"""
        task_id = event["task_id"]
        event_type = event["type"]
        job = await self.get_job(task_id)
        if job is None:
            return
        platform = job["platform"]
        persisted: dict[str, Any]

        if event_type == "status":
            persisted = await self._persist_status(
                task_id,
                platform,
                event["status"],
                event_type="status",
                data={"status": event["status"]},
            )
        elif event_type == "log":
            persisted = await self._persist_status(
                task_id,
                platform,
                job["status"],
                event_type="log",
                message=event.get("message", ""),
                level=event.get("level", "INFO"),
                data={"timestamp": event.get("timestamp"), "source_sequence": event.get("sequence")},
            )
        elif event_type == "result":
            account = event.get("account")
            if account:
                from worker.tasks.registration import save_registered_account

                await save_registered_account(**account)
            result = event.get("data")
            if not isinstance(result, dict):
                persisted = await self._persist_status(
                    task_id,
                    platform,
                    "failed",
                    event_type="failed",
                    error="任务返回结果必须是对象",
                    data={"result_type": type(result).__name__},
                )
            else:
                success = bool(result.get("success", False))
                persisted = await self._persist_status(
                    task_id,
                    platform,
                    "succeeded" if success else "failed",
                    event_type="result",
                    result=result,
                    error=None if success else result.get("error") or "任务返回未成功结果",
                    data=result,
                )
        elif event_type == "failed":
            persisted = await self._persist_status(
                task_id,
                platform,
                "failed",
                event_type="failed",
                error=event["error"],
                message=event["error"],
                data={"traceback": event.get("traceback")},
            )
        elif event_type == "done":
            current = await self.get_job(task_id)
            if current is None:
                return
            if current["status"] not in TERMINAL_STATUSES:
                persisted = await self._persist_status(
                    task_id,
                    platform,
                    "failed",
                    event_type="done",
                    error="任务进程已退出但未返回结果",
                )
            else:
                persisted = await self._persist_status(
                    task_id,
                    platform,
                    current["status"],
                    event_type="done",
                )
        else:
            return

        await self._broadcast(task_id, persisted)
        if event_type == "done":
            process = self._processes.pop(task_id, None)
            self._clean_exit_since.pop(task_id, None)
            if process is not None:
                process.join(timeout=1)
            await self._start_pending()

    async def _reap_processes(self) -> None:
        for task_id, process in list(self._processes.items()):
            if process.is_alive():
                self._clean_exit_since.pop(task_id, None)
                continue
            process.join(timeout=0)
            if process.exitcode not in (0, None):
                await self._fail_reaped_process(
                    task_id, f"任务进程异常退出（exit code {process.exitcode}）"
                )
                continue
            # multiprocessing.Queue 的 feeder 线程可能在子进程退出后才送达 done。
            # 给予一个短暂观察窗口，超过后仍未收到 done 才释放并发槽位。
            exited_since = self._clean_exit_since.setdefault(task_id, time.monotonic())
            if time.monotonic() - exited_since >= 2:
                await self._fail_reaped_process(task_id, "任务进程已退出但未返回完成事件")

    async def _fail_reaped_process(self, task_id: str, error: str) -> None:
        job = await self.get_job(task_id)
        if job is not None and job["status"] not in TERMINAL_STATUSES:
            persisted = await self._persist_status(
                task_id,
                job["platform"],
                "failed",
                event_type="failed",
                error=error,
            )
            await self._broadcast(task_id, persisted)
        self._processes.pop(task_id, None)
        self._clean_exit_since.pop(task_id, None)
        await self._start_pending()

    async def _persist_status(
        self,
        task_id: str,
        platform: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        event_type: str = "status",
        message: str | None = None,
        level: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """持久化事件和状态投影；仅在事务提交后返回可广播事件。"""
        from app.core.dependencies import db
        from gateway.registration_jobs import RegistrationJobService, serialize_event_envelope

        async with db.get_session() as session:
            event = await RegistrationJobService(session).append_event(
                task_id,
                platform=platform,
                event_type=event_type,
                status=status,
                result=result,
                error_message=error,
                message=message,
                level=level,
                data=data,
            )
            return serialize_event_envelope(event)

    async def _broadcast(self, task_id: str, event: dict[str, Any]) -> None:
        for subscription in tuple(self._subscribers.get(task_id, ())):
            try:
                subscription.put_nowait(event)
            except asyncio.QueueFull:
                # 日志可以丢弃；持久化终态必须优先替换一条非终态实时消息。
                event_type = event.get("data", {}).get("event_type")
                if event_type in {"result", "failed", "done", "interrupted"}:
                    queued_log = next(
                        (
                            queued
                            for queued in subscription._queue
                            if queued.get("data", {}).get("event_type")
                            not in {"result", "failed", "done", "interrupted"}
                        ),
                        None,
                    )
                    if queued_log is not None:
                        subscription._queue.remove(queued_log)
                        subscription.put_nowait(event)
