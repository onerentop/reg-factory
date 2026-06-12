import os

import httpx as _httpx
from fastapi import APIRouter, HTTPException

from shared.base_schema import ApiResponse
from gateway.deps import _ACCOUNT_URL

router = APIRouter()


@router.post("/tools/unlock-outlook", response_model=ApiResponse)
async def unlock_outlook(body: dict):
    from worker.tasks import unlock_outlook_account
    task = unlock_outlook_account.delay(body["email"], body["password"])
    return ApiResponse(data={"task_id": task.id, "status": "queued"})


@router.post("/tools/validate-keys", response_model=ApiResponse)
async def validate_keys(body: dict):
    from worker.tasks import validate_session_key
    task = validate_session_key.delay(body["key"])
    return ApiResponse(data={"task_id": task.id, "status": "queued"})


@router.post("/tools/extract-graph-token", response_model=ApiResponse)
async def extract_graph_token_api(body: dict):
    """提取 Outlook Graph API refresh_token（纯 HTTP，无需浏览器）。
    传 account_id 自动从 Account Service 查密码；或直接传 email+password。"""
    email = body.get("email", "")
    password = body.get("password", "")
    account_id = body.get("account_id", "")

    if account_id and not password:
        try:
            async with _httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{_ACCOUNT_URL}/accounts/{account_id}")
                acct = resp.json().get("data", {})
                email = email or acct.get("email", "")
                password = acct.get("password", "")
        except Exception:
            pass

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")

    import asyncio
    from worker.legacy_bridge import LegacyBridge
    bridge = LegacyBridge()
    bridge.ensure_importable()
    try:
        import config as _lc  # noqa
    except Exception:
        pass

    if not os.environ.get("HTTPS_PROXY"):
        proxy_for_token = ""
        try:
            async with _httpx.AsyncClient(timeout=5) as _pc:
                _pr = await _pc.get("http://localhost:8000/proxy")
                _pl = _pr.json().get("data", [])
                _active = [p for p in _pl if p.get("status") in ("active", "available")]
                if _active:
                    _s = _active[0]
                    _u = _s.get("username", "")
                    _pw = _s.get("password", "")
                    _auth = f"{_u}:{_pw}@" if _u and _pw else ""
                    proxy_for_token = f"{_s.get('type','socks5')}://{_auth}{_s['host']}:{_s['port']}"
        except Exception:
            pass
        if proxy_for_token:
            os.environ["HTTPS_PROXY"] = proxy_for_token
            os.environ["HTTP_PROXY"] = proxy_for_token
        else:
            os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:7897")
            os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:7897")

    from extract_graph_tokens import get_graph_token
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, get_graph_token, email, password, 0)

    if result and result.get("refresh_token"):
        client_id = result.get("client_id", "9e5f94bc-e8a4-4e73-b8be-63364c29d753")
        if account_id:
            try:
                async with _httpx.AsyncClient(timeout=10) as client:
                    await client.put(f"{_ACCOUNT_URL}/accounts/{account_id}", json={
                        "tokens": {
                            "refresh_token": result["refresh_token"],
                            "client_id": client_id,
                        },
                    })
            except Exception:
                pass
        return ApiResponse(data={
            "success": True, "email": email,
            "client_id": client_id,
            "refresh_token": result["refresh_token"][:20] + "...",
        })

    return ApiResponse(data={"success": False, "email": email, "error": str(result) if result else "Failed to get token"})


@router.post("/tools/activate-plus", response_model=ApiResponse)
async def activate_plus(body: dict):
    from worker.tasks import activate_plus_account
    task = activate_plus_account.delay(body["access_token"], body["email"], body.get("card", ""))
    return ApiResponse(data={"task_id": task.id, "status": "queued"})
