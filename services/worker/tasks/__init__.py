from worker.celery_app import celery_app  # noqa: F401

# 导入所有子模块，确保 @celery_app.task 装饰器运行（任务注册）
from worker.tasks.maintenance import (  # noqa: F401
    check_proxy_health,
    check_sms_balance,
    cleanup_old_logs,
    planned_registration,
)
from worker.tasks.registration import (  # noqa: F401
    register_outlook_single,
    register_account,
    retry_from_step,
)
from worker.tasks.tools import (  # noqa: F401
    unlock_outlook_account,
    validate_session_key,
    activate_plus_account,
)
from worker.tasks.orchestrate import (  # noqa: F401
    register_all_platforms,
    full_flow,
)
