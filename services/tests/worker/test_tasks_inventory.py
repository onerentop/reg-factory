"""仅保留 Outlook / Google 注册处理器的导出不变量。"""

import inspect

import worker.tasks as tasks


EXPECTED_HANDLERS = {
    "register_account",
    "register_outlook_single",
    "retry_from_step",
}


def test_registration_task_handlers_are_exported():
    for name in EXPECTED_HANDLERS:
        assert callable(getattr(tasks, name, None)), f"worker.tasks 缺少处理器：{name}"


def test_removed_tool_and_maintenance_handlers_are_not_exported():
    for name in ("validate_session_key", "planned_registration", "cleanup_old_logs"):
        assert not hasattr(tasks, name)


def test_task_handlers_use_plain_function_signatures():
    assert tuple(inspect.signature(tasks.register_outlook_single).parameters) == (
        "idx",
        "proxy",
        "config",
    )
