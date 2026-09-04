import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from account_service.repository import AccountRepository, StepRepository
from account_service.schemas import AccountUpdate
from account_service.service import AccountService
from gateway.deps import get_session
from gateway.models import ProxyEntry
from shared.base_schema import ApiResponse

router = APIRouter()


def _proxy_url(proxy: ProxyEntry) -> str:
    auth = f"{proxy.username}:{proxy.password}@" if proxy.username and proxy.password else ""
    return f"{proxy.type or 'socks5'}://{auth}{proxy.host}:{proxy.port}"


async def _get_account_service(session: AsyncSession) -> AccountService:
    return AccountService(AccountRepository(session), StepRepository(session))


@router.post("/tools/extract-graph-token", response_model=ApiResponse)
async def extract_graph_token_api(body: dict, session: AsyncSession = Depends(get_session)):
    """为已保存的 Outlook 账号提取并持久化 Graph refresh token。"""
    email = body.get("email", "")
    password = body.get("password", "")
    account_id = body.get("account_id", "")
    account_service = await _get_account_service(session)

    if account_id:
        try:
            account = await account_service.get_account(str(uuid.UUID(account_id)))
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid account_id") from error
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if account.platform != "outlook":
            raise HTTPException(status_code=422, detail="Graph token extraction supports Outlook accounts only")
        email = email or account.email
        password = password or account.password or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")

    proxy = ""
    result = await session.execute(select(ProxyEntry))
    active = next((item for item in result.scalars() if item.status in {"active", "available"}), None)
    if active is not None:
        proxy = _proxy_url(active).replace("socks5://", "socks5h://", 1)
        from common.proxy import rotate_proxy_sid

        proxy = rotate_proxy_sid(proxy)

    from worker.legacy_bridge import LegacyBridge

    LegacyBridge().ensure_importable()
    from extract_graph_tokens import get_graph_token

    result = await asyncio.get_running_loop().run_in_executor(
        None, get_graph_token, email, password, 0, proxy
    )
    if not result or not result.get("refresh_token"):
        return ApiResponse(data={
            "success": False,
            "email": email,
            "error": str(result) if result else "Failed to get token",
        })

    client_id = result.get("client_id", "9e5f94bc-e8a4-4e73-b8be-63364c29d753")
    if account_id:
        await account_service.update_account(str(uuid.UUID(account_id)), AccountUpdate(tokens={
            "refresh_token": result["refresh_token"],
            "client_id": client_id,
        }))
    return ApiResponse(data={
        "success": True,
        "email": email,
        "client_id": client_id,
        "refresh_token": result["refresh_token"][:20] + "...",
    })
