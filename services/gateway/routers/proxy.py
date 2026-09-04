from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from shared.base_schema import ApiResponse
from gateway.models import ProxyEntry
from gateway.deps import get_session
from gateway.schemas import ProxyImportRequest, ProxyStatusUpdate, ProxyUpdate, ProxyWrite

router = APIRouter()


@router.get("/proxy", response_model=ApiResponse)
async def list_proxies(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(select(ProxyEntry).order_by(ProxyEntry.created_at.desc()))
    proxies = result.scalars().all()
    return ApiResponse(data=[{
        "id": str(p.id), "type": p.type, "host": p.host, "port": p.port,
        "username": p.username, "has_password": bool(p.password), "status": p.status,
        "region": p.region,
    } for p in proxies])


@router.post("/proxy", response_model=ApiResponse)
async def add_proxy(body: ProxyWrite, session: AsyncSession = Depends(get_session)):
    proxy = ProxyEntry(
        type=body.type, host=body.host, port=body.port,
        username=body.username, password=body.password,
        region=body.region, status=body.status,
    )
    session.add(proxy)
    await session.flush()
    await session.refresh(proxy)
    return ApiResponse(data={"id": str(proxy.id)})


@router.put("/proxy/{proxy_id}", response_model=ApiResponse)
async def update_proxy(proxy_id: str, body: ProxyUpdate, session: AsyncSession = Depends(get_session)):
    """修改代理配置。"""
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(proxy, field, value)
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
async def update_proxy_status(proxy_id: str, body: ProxyStatusUpdate, session: AsyncSession = Depends(get_session)):
    import uuid
    from sqlalchemy import select
    stmt = select(ProxyEntry).where(ProxyEntry.id == uuid.UUID(proxy_id))
    result = await session.execute(stmt)
    proxy = result.scalar_one_or_none()
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    proxy.status = body.status
    await session.flush()
    return ApiResponse(data={"id": str(proxy.id), "status": proxy.status})


@router.post("/proxy/import", response_model=ApiResponse)
async def import_proxies(body: ProxyImportRequest, session: AsyncSession = Depends(get_session)):
    """批量导入代理文本。按 (host, port) 去重，逐行报告非法项。"""
    from sqlalchemy import select
    from gateway.proxy_import import parse_proxy_lines

    drafts, invalid = parse_proxy_lines(body.text, body.type)

    existing: set[tuple[str, int]] = set()
    if body.skip_duplicates:
        result = await session.execute(select(ProxyEntry))
        existing = {(p.host, int(p.port)) for p in result.scalars().all()}

    imported, duplicates = 0, 0
    for draft in drafts:
        if (draft.host, draft.port) in existing:
            duplicates += 1
            continue
        # status 必须显式设 active：模型默认 'unknown' 不在可抢占状态里，
        # 漏设会让导入的代理永远分配不出去且无任何报错。
        session.add(ProxyEntry(
            type=draft.type, host=draft.host, port=draft.port,
            username=draft.username, password=draft.password, status="active",
        ))
        existing.add((draft.host, draft.port))
        imported += 1
    await session.flush()

    return ApiResponse(data={
        "imported": imported,
        "duplicates": duplicates,
        "invalid": [{"line_no": i.line_no, "raw": i.raw, "reason": i.reason} for i in invalid],
    })
