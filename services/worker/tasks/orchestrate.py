from worker.celery_app import celery_app


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
