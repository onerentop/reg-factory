from worker.celery_app import celery_app


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
