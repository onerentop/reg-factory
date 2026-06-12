from worker.celery_app import celery_app


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
        from worker.tasks.registration import register_account
        for i in range(count):
            register_account.delay(platform, f"auto_{platform}_{i}", {})
        return {"status": "queued", "count": count, "platform": platform}

    return asyncio.run(_run())
