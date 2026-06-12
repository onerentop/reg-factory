from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from shared.base_schema import ApiResponse
from gateway.models import ProxyEntry
from gateway.deps import get_session

router = APIRouter()


@router.get("/proxy", response_model=ApiResponse)
async def list_proxies(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(select(ProxyEntry).order_by(ProxyEntry.created_at.desc()))
    proxies = result.scalars().all()
    return ApiResponse(data=[{
        "id": str(p.id), "type": p.type, "host": p.host, "port": p.port,
        "username": p.username, "password": p.password, "status": p.status,
    } for p in proxies])


@router.post("/proxy", response_model=ApiResponse)
async def add_proxy(body: dict, session: AsyncSession = Depends(get_session)):
    proxy = ProxyEntry(
        type=body.get("type", "socks5"), host=body["host"], port=int(body["port"]),
        username=body.get("username"), password=body.get("password"),
        region=body.get("region"), status=body.get("status", "active"),
    )
    session.add(proxy)
    await session.flush()
    await session.refresh(proxy)
    from shared.audit import AuditRecorder
    AuditRecorder().record(operator="system", action="add_proxy", target=body.get("host", ""))
    return ApiResponse(data={"id": str(proxy.id)})


@router.put("/proxy/{proxy_id}", response_model=ApiResponse)
async def update_proxy(proxy_id: str, body: dict, session: AsyncSession = Depends(get_session)):
    """修改代理配置。"""
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    for field in ("type", "host", "port", "username", "password"):
        if field in body:
            setattr(proxy, field, int(body[field]) if field == "port" else body[field])
    await session.flush()
    return ApiResponse(data={"id": str(proxy.id)})


@router.delete("/proxy/{proxy_id}", response_model=ApiResponse)
async def delete_proxy(proxy_id: str, session: AsyncSession = Depends(get_session)):
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    await session.delete(proxy)
    await session.flush()
    from shared.audit import AuditRecorder
    recorder = AuditRecorder()
    recorder.record(operator="system", action="delete_proxy", target=proxy_id)
    return ApiResponse(message="Deleted")


@router.post("/proxy/{proxy_id}/test", response_model=ApiResponse)
async def test_proxy(proxy_id: str, session: AsyncSession = Depends(get_session)):
    """真实检测代理连通性。"""
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")

    from gateway.proxy_manager import check_proxy_health, detect_proxy_ip
    ptype = proxy.type or "socks5"
    result = await check_proxy_health(proxy.host, int(proxy.port), ptype,
                                       username=proxy.username, password=proxy.password)
    ip_info = {"ip": "", "region": ""}
    if result in ("available", "slow"):
        ip_info = await detect_proxy_ip(proxy.host, int(proxy.port), ptype,
                                         username=proxy.username, password=proxy.password)
    return ApiResponse(data={"id": str(proxy.id), "result": result, **ip_info})


@router.put("/proxy/{proxy_id}/status", response_model=ApiResponse)
async def update_proxy_status(proxy_id: str, body: dict, session: AsyncSession = Depends(get_session)):
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    proxy.status = body.get("status", proxy.status)
    await session.flush()
    return ApiResponse(data={"id": str(proxy.id), "status": proxy.status})
