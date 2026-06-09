from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_schema import ApiResponse
from sms_service.schemas import AcquireRequest, PlatformConfigWrite
from sms_service.service import SmsService
from sms_service.repository import SmsOrderRepository, SmsPlatformConfigRepository

router = APIRouter(prefix="/sms", tags=["sms"])


def get_service(session: AsyncSession) -> SmsService:
    return SmsService(
        order_repo=SmsOrderRepository(session),
        config_repo=SmsPlatformConfigRepository(session),
    )


@router.get("/providers", response_model=ApiResponse)
async def list_providers():
    from sms_service.providers.base import ProviderRegistry
    return ApiResponse(data=ProviderRegistry.list_providers())


@router.get("/providers/{name}/balance", response_model=ApiResponse)
async def get_balance(name: str, session: AsyncSession = Depends()):
    service = get_service(session)
    try:
        result = await service.get_balance(name)
        return ApiResponse(data=result.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/number/acquire", response_model=ApiResponse)
async def acquire_number(body: AcquireRequest, session: AsyncSession = Depends()):
    service = get_service(session)
    try:
        result = await service.acquire_number(
            body.service, body.country, body.provider
        )
        return ApiResponse(data={
            "order_id": result.order_id,
            "phone_number": result.phone_number,
            "provider": result.provider,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/number/{order_id}/code", response_model=ApiResponse)
async def get_code(order_id: str, timeout: int = 120, session: AsyncSession = Depends()):
    service = get_service(session)
    try:
        result = await service.get_code(order_id, timeout)
        return ApiResponse(data={
            "order_id": result.order_id,
            "code": result.code,
            "status": result.status.value,
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/number/{order_id}/complete", response_model=ApiResponse)
async def complete_order(order_id: str, session: AsyncSession = Depends()):
    service = get_service(session)
    try:
        await service.complete(order_id)
        return ApiResponse(message="Completed")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/number/{order_id}/cancel", response_model=ApiResponse)
async def cancel_order(order_id: str, session: AsyncSession = Depends()):
    service = get_service(session)
    try:
        await service.cancel(order_id)
        return ApiResponse(message="Cancelled")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/config", response_model=ApiResponse)
async def get_configs(session: AsyncSession = Depends()):
    service = get_service(session)
    configs = await service.get_platform_configs()
    return ApiResponse(data=[c.model_dump() for c in configs])


@router.put("/config/{provider_name}", response_model=ApiResponse)
async def save_config(
    provider_name: str, body: PlatformConfigWrite, session: AsyncSession = Depends()
):
    service = get_service(session)
    result = await service.save_platform_config(
        provider_name=provider_name,
        display_name=body.display_name or provider_name,
        enabled=body.enabled,
        priority=body.priority,
        config=body.config,
    )
    return ApiResponse(data=result.model_dump())
