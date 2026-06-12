"""Celery 任务不变量：把 worker/tasks.py 拆成 tasks/ 包前后，
① 注册的任务名集合、② 可从 worker.tasks import 的任务函数，都必须完全不变。
gateway 的 tools/orchestrate router 按名 `from worker.tasks import xxx`，
`celery -A worker.tasks` 也需 celery_app 在 worker.tasks —— 此测试是拆分安全网。
"""

import os

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import worker.tasks as t
from worker.tasks import celery_app

EXPECTED_TASKS = {
    "activate_plus_account",
    "check_proxy_health",
    "check_sms_balance",
    "cleanup_old_logs",
    "full_flow",
    "planned_registration",
    "register_account",
    "register_all_platforms",
    "register_outlook_single",
    "retry_from_step",
    "unlock_outlook_account",
    "validate_session_key",
}

# gateway router 按名 import 的任务函数，拆分后必须仍可从 worker.tasks 取
GATEWAY_IMPORTED = (
    "unlock_outlook_account",
    "validate_session_key",
    "activate_plus_account",
    "register_all_platforms",
    "full_flow",
)


def test_all_tasks_registered():
    names = {n for n in celery_app.tasks if not n.startswith("celery.")}
    assert names == EXPECTED_TASKS


def test_gateway_imported_tasks_present():
    for name in GATEWAY_IMPORTED:
        assert hasattr(t, name), f"worker.tasks 缺导出 {name}（gateway 依赖它）"
