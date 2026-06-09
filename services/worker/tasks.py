import os
import random
from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _fetch_proxy_from_manager() -> str:
    """从 Gateway 代理管理获取一个激活的代理，格式化为 URL。"""
    import requests as _req
    try:
        resp = _req.get("http://localhost:8000/proxy", timeout=5)
        proxy_list = resp.json().get("data", [])
        available = [p for p in proxy_list if p.get("status") in ("active", "available")]
        if available:
            selected = random.choice(available)
            ptype = selected.get("type", "socks5")
            host = selected.get("host", "")
            port = selected.get("port", "")
            user = selected.get("username", "")
            pwd = selected.get("password", "")
            if user and pwd:
                return f"{ptype}://{user}:{pwd}@{host}:{port}"
            return f"{ptype}://{host}:{port}"
    except Exception:
        pass
    return ""

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
    "planned-registration": {
        "task": "planned_registration",
        "schedule": crontab(minute=0, hour="*/6"),
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


@celery_app.task(name="register_outlook_new", bind=True)
def register_outlook_new(self, count: int = 1, proxy: str = "", config: dict = None):
    """从前端触发的 Outlook 新账号注册。自动生成邮箱，从代理管理获取代理。"""
    import asyncio
    from worker.step_engine import FlowRegistry
    from worker.legacy_bridge import LegacyBridge

    bridge = LegacyBridge()
    bridge.ensure_importable()
    try:
        import config as _legacy_config  # noqa: F401
    except Exception:
        pass

    if not proxy:
        proxy = _fetch_proxy_from_manager()

    print(f"[register_outlook_new] proxy={'yes: ' + proxy[:30] + '...' if proxy else 'NONE'}, count={count}")

    from worker.log_capture import LogCapture
    task_id = self.request.id or "unknown"
    capture = LogCapture(task_id=task_id, redis_url=redis_url).start()

    async def _run():
        import httpx
        results = []
        for i in range(count):
            flow = FlowRegistry.get("outlook")
            context = {"idx": i, "proxy": proxy, **(config or {})}
            step_results = await flow.run(context)
            success = all(r.success for r in step_results)
            email = context.get("email", "")
            password = context.get("password", "")

            if success and email:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        create_resp = await client.post("http://localhost:8002/accounts", json={
                            "email": email,
                            "password": password,
                            "platform": "outlook",
                            "total_steps": len(step_results),
                            "metadata": {
                                "refresh_token": context.get("refresh_token", ""),
                                "client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
                                "proxy": proxy[:30] if proxy else "",
                            },
                        })
                        account_data = create_resp.json().get("data", {})
                        account_id = account_data.get("id")
                        if account_id:
                            raw_token = context.get("refresh_token", "")
                            if isinstance(raw_token, dict):
                                refresh_token = raw_token.get("refresh_token", "")
                            else:
                                refresh_token = str(raw_token) if raw_token else ""
                            await client.put(f"http://localhost:8002/accounts/{account_id}", json={
                                "status": "success",
                                "current_step": len(step_results),
                                "tokens": {
                                    "refresh_token": refresh_token,
                                    "client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
                                } if refresh_token else None,
                            })
                    print(f"[register_outlook_new] saved to Account Service: {email}")
                except Exception as e:
                    print(f"[register_outlook_new] failed to save to Account Service: {e}")

            results.append({
                "index": i,
                "success": success,
                "email": email,
                "has_token": bool(context.get("refresh_token")),
                "steps": [{"name": r.name, "success": r.success, "error": r.error, "duration_ms": r.duration_ms} for r in step_results],
            })
        return {"count": count, "results": results}

    try:
        return asyncio.run(_run())
    finally:
        capture.stop()


@celery_app.task(name="register_account", bind=True)
def register_account(self, platform: str, email: str, config: dict):
    """通用注册任务。所有平台走代理管理获取代理。"""
    import asyncio
    from worker.step_engine import FlowRegistry

    proxy = config.get("proxy", "") or _fetch_proxy_from_manager()
    context = {"email": email, "proxy": proxy, **config}

    async def _run():
        flow = FlowRegistry.get(platform)
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


@celery_app.task(name="planned_registration")
def planned_registration():
    """计划注册——按配置自动启动批量注册任务。"""
    import asyncio

    async def _run():
        from shared.config_client import ConfigClient
        client = ConfigClient()
        await client.load_from_service()
        plan = client.get("registration.plan", {})
        if not plan.get("enabled"):
            return {"status": "skipped", "reason": "plan not enabled"}
        count = plan.get("count", 5)
        platform = plan.get("platform", "outlook")
        for i in range(count):
            register_account.delay(platform, f"auto_{platform}_{i}", {})
        return {"status": "queued", "count": count, "platform": platform}

    return asyncio.run(_run())


@celery_app.task(name="unlock_outlook_account", bind=True)
def unlock_outlook_account(self, email: str, password: str, config: dict = None):
    """解锁被锁定的 Outlook 账号。通过 LegacyBridge 调用 unlock_outlook.py。"""
    import asyncio
    from worker.legacy_bridge import LegacyBridge
    bridge = LegacyBridge()
    bridge.ensure_importable()

    async def _run():
        from unlock_outlook import unlock_one
        result = await unlock_one(email, password, idx=0)
        return {"email": email, "unlocked": bool(result)}

    return asyncio.run(_run())


@celery_app.task(name="validate_session_key", bind=True)
def validate_session_key(self, session_key: str, config: dict = None):
    """验证 Claude sessionKey 是否有效。通过 LegacyBridge 调用 validate_keys.py。"""
    import asyncio
    from worker.legacy_bridge import LegacyBridge
    bridge = LegacyBridge()
    bridge.ensure_importable()

    async def _run():
        from validate_keys import validate_key
        from common.browser_provider import get_browser_provider
        bb = get_browser_provider()
        valid = await validate_key(session_key, bb)
        return {"key": session_key[:16] + "...", "valid": valid}

    return asyncio.run(_run())


@celery_app.task(name="activate_plus_account", bind=True)
def activate_plus_account(self, access_token: str, email: str, card: str = ""):
    """用卡密激活 ChatGPT Plus。通过 LegacyBridge 调用 activate_plus.py 逻辑。"""
    from worker.legacy_bridge import LegacyBridge
    bridge = LegacyBridge()
    bridge.ensure_importable()

    try:
        from common.plus_baxi import try_activate
        result = try_activate(access_token, card)
        return {"email": email, "activated": result.get("success", False), "detail": str(result)[:200]}
    except Exception as e:
        return {"email": email, "activated": False, "error": str(e)}


@celery_app.task(name="register_all_platforms", bind=True)
def register_all_platforms(self, email: str, password: str, platforms: list = None, config: dict = None):
    """多平台编排：一个邮箱顺序注册多个平台。"""
    import asyncio
    from worker.step_engine import FlowRegistry

    if platforms is None:
        platforms = ["claude", "chatgpt", "grok"]

    async def _run():
        results = {}
        for platform in platforms:
            try:
                flow = FlowRegistry.get(platform)
                context = {"email": email, "password": password, **(config or {})}
                step_results = await flow.run(context)
                success = all(r.success for r in step_results)
                results[platform] = {
                    "success": success,
                    "steps": [{
                        "name": r.name, "success": r.success,
                        "error": r.error, "duration_ms": r.duration_ms,
                    } for r in step_results],
                }
            except Exception as e:
                results[platform] = {"success": False, "error": str(e)}
        return {"email": email, "platforms": results}

    return asyncio.run(_run())


@celery_app.task(name="full_flow", bind=True)
def full_flow(self, count: int = 1, platforms: list = None, config: dict = None):
    """端到端全流程：Outlook 注册 → 多平台注册。"""
    import asyncio
    from worker.step_engine import FlowRegistry

    if platforms is None:
        platforms = ["claude", "chatgpt", "grok"]

    async def _run():
        results = []
        for i in range(count):
            outlook_flow = FlowRegistry.get("outlook")
            outlook_ctx = {"idx": i, **(config or {})}
            outlook_results = await outlook_flow.run(outlook_ctx)

            outlook_success = all(r.success for r in outlook_results)
            if not outlook_success:
                results.append({
                    "index": i, "outlook": False,
                    "error": next((r.error for r in outlook_results if not r.success), "Unknown"),
                })
                continue

            email = outlook_ctx.get("email", "")
            password = outlook_ctx.get("password", "")
            if not email:
                results.append({"index": i, "outlook": True, "error": "No email in context"})
                continue

            platform_results = {}
            for platform in platforms:
                try:
                    flow = FlowRegistry.get(platform)
                    ctx = {"email": email, "password": password, **(config or {})}
                    step_results = await flow.run(ctx)
                    platform_results[platform] = all(r.success for r in step_results)
                except Exception as e:
                    platform_results[platform] = False

            results.append({
                "index": i, "email": email,
                "outlook": True, "platforms": platform_results,
            })

        return {"count": count, "results": results}

    return asyncio.run(_run())
