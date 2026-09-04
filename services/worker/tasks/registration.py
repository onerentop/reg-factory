import asyncio
from collections.abc import Callable
from typing import Any

from worker.tasks._helpers import rotate_proxy_sid


async def save_registered_account(
    email: str,
    password: str,
    platform: str,
    proxy: str,
    step_count: int,
    refresh_token: object,
) -> None:
    """Worker 直接复用账户领域服务，避免回环调用本机 HTTP API。"""
    from account_service.repository import AccountRepository, StepRepository
    from account_service.schemas import AccountCreate, AccountUpdate
    from account_service.service import AccountService
    from app.core.dependencies import db

    raw_token = refresh_token.get("refresh_token", "") if isinstance(refresh_token, dict) else refresh_token
    token_value = str(raw_token) if raw_token else ""
    async with db.get_session() as session:
        service = AccountService(AccountRepository(session), StepRepository(session))
        account = await service.create_account(AccountCreate(
            email=email,
            password=password,
            platform=platform,
            total_steps=step_count,
            proxy_used=proxy[:30] if proxy else None,
            metadata={"client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753"},
        ))
        await service.update_account(
            account.id,
            AccountUpdate(
                status="success",
                current_step=step_count,
                tokens={
                    "refresh_token": token_value,
                    "client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
                } if token_value else None,
            ),
        )


async def execute_registration(
    task_id: str,
    platform: str,
    *,
    idx: int = 0,
    proxy: str = "",
    config: dict[str, Any] | None = None,
    email: str = "",
    from_step: int = 0,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """在独立子进程执行既有注册流程，不直接写任务状态或 SQLite。"""
    from worker.legacy_bridge import LegacyBridge
    from worker.step_engine import FlowRegistry

    LegacyBridge().ensure_importable()
    proxy = rotate_proxy_sid(proxy)

    context = {"idx": idx, "proxy": proxy, **(config or {})}
    if email:
        context["email"] = email
    if emit is not None:
        emit({"type": "status", "task_id": task_id, "status": "running", "platform": platform})

    flow = FlowRegistry.get(platform)
    results = await flow.run(context, from_step=from_step)
    success = bool(results) and all(result.success for result in results)
    account_email = str(context.get("email", ""))
    password = str(context.get("password", ""))
    payload = {
        "success": success,
        "task_id": task_id,
        "platform": platform,
        "email": account_email,
        "has_token": bool(context.get("refresh_token")),
        "steps": [
            {
                "step": result.step_number,
                "name": result.name,
                "success": result.success,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }
            for result in results
        ],
    }
    account = None
    if success and account_email:
        account = {
            "email": account_email,
            "password": password,
            "platform": platform,
            "proxy": proxy,
            "step_count": len(results),
            "refresh_token": context.get("refresh_token", ""),
        }
    return payload, account


def register_platform(
    platform: str,
    idx: int = 0,
    proxy: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """兼容旧 Python 调用；HTTP API 应通过 LocalProcessTaskManager 提交任务。"""
    result, _ = asyncio.run(
        execute_registration("local-direct", platform, idx=idx, proxy=proxy, config=config)
    )
    return result


def register_outlook_single(
    idx: int = 0, proxy: str = "", config: dict[str, Any] | None = None
) -> dict[str, Any]:
    return register_platform("outlook", idx=idx, proxy=proxy, config=config)


def register_account(platform: str, email: str, config: dict[str, Any]) -> dict[str, Any]:
    result, _ = asyncio.run(
        execute_registration(
            "local-direct",
            platform,
            proxy=config.get("proxy", ""),
            config=config,
            email=email,
        )
    )
    return result


def retry_from_step(
    platform: str, email: str, from_step: int, config: dict[str, Any]
) -> dict[str, Any]:
    result, _ = asyncio.run(
        execute_registration(
            "local-direct",
            platform,
            proxy=config.get("proxy", ""),
            config=config,
            email=email,
            from_step=from_step,
        )
    )
    return result
