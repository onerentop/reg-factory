import os
from celery import Celery
from celery.schedules import crontab

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
    "planned-registration": {
        "task": "planned_registration",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}
