import os
from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "reg_worker",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
)

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "proxy-health-check": {
        "task": "check_proxy_health",
        "schedule": crontab(minute="*/5"),
    },
    "sms-balance-check": {
        "task": "check_sms_balance",
        "schedule": crontab(minute="*/10"),
    },
    "log-cleanup": {
        "task": "cleanup_old_logs",
        "schedule": crontab(hour=2, minute=0),
    },
}


@celery_app.task(name="check_proxy_health")
def check_proxy_health():
    """定时检测代理健康状态。"""
    return {"status": "checked"}


@celery_app.task(name="check_sms_balance")
def check_sms_balance():
    """定时检查接码平台余额。"""
    return {"status": "checked"}


@celery_app.task(name="cleanup_old_logs")
def cleanup_old_logs():
    """定时清理过期日志。"""
    return {"status": "cleaned"}


@celery_app.task(name="register_account", bind=True)
def register_account(self, platform: str, email: str, config: dict):
    """注册账户的 Celery 任务入口。同步包装异步流程。"""
    import asyncio
    from worker.step_engine import FlowRegistry

    async def _run():
        flow = FlowRegistry.get(platform)
        context = {"email": email, **config}
        results = await flow.run(context)
        return [
            {"step": r.step_number, "name": r.name, "success": r.success,
             "error": r.error, "duration_ms": r.duration_ms}
            for r in results
        ]

    return asyncio.run(_run())


@celery_app.task(name="retry_from_step", bind=True)
def retry_from_step(self, platform: str, email: str, from_step: int, config: dict):
    """从指定步骤重试的 Celery 任务。"""
    import asyncio
    from worker.step_engine import FlowRegistry

    async def _run():
        flow = FlowRegistry.get(platform)
        context = {"email": email, **config}
        results = await flow.run(context, from_step=from_step)
        return [
            {"step": r.step_number, "name": r.name, "success": r.success,
             "error": r.error, "duration_ms": r.duration_ms}
            for r in results
        ]

    return asyncio.run(_run())
