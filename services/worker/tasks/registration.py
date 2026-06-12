import os

from worker.celery_app import celery_app, redis_url
from worker.tasks._helpers import _fetch_proxy_from_manager, rotate_proxy_sid


@celery_app.task(name="register_outlook_single", bind=True)
def register_outlook_single(self, idx: int = 0, proxy: str = "", config: dict = None):
    """单号 Outlook 注册任务。每个任务独立注册一个账号。"""
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
    # 每次注册轮换 sid → 新出口 IP(规避 sid 复用失效 + 多 task 并发同 IP)
    proxy = rotate_proxy_sid(proxy)

    print(f"[outlook#{idx}] proxy={'yes: ' + proxy[:30] + '...' if proxy else 'NONE'}")

    from worker.log_capture import LogCapture
    task_id = self.request.id or "unknown"
    capture = LogCapture(task_id=task_id, redis_url=redis_url).start()

    async def _run():
        import httpx
        flow = FlowRegistry.get("outlook")
        context = {"idx": idx, "proxy": proxy, **(config or {})}
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
                print(f"[outlook#{idx}] saved: {email}")
            except Exception as e:
                print(f"[outlook#{idx}] save failed: {e}")

        return {
            "success": success,
            "email": email,
            "has_token": bool(context.get("refresh_token")),
            "steps": [{"name": r.name, "success": r.success, "error": r.error, "duration_ms": r.duration_ms} for r in step_results],
        }

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
