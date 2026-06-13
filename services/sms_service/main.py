import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import DatabaseManager
from shared.log_handler import setup_logger

db = DatabaseManager(
    url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///regfactory_dev.db")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from shared.base_model import BaseModel
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    logger = setup_logger("sms_service")
    logger.info("SMS Service starting")
    yield
    await db.close()


app = FastAPI(title="RegFactory SMS Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_session():
    async with db.get_session() as session:
        yield session


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sms_service"}


# Import providers to trigger @register decorators
import sms_service.providers  # noqa: F401, E402

from sms_service.service import SmsService  # noqa: E402
from sms_service.repository import SmsOrderRepository, SmsPlatformConfigRepository  # noqa: E402
from shared.base_schema import ApiResponse  # noqa: E402
from sms_service.schemas import AcquireRequest, PlatformConfigWrite  # noqa: E402
from sms_service.providers.base import ProviderRegistry  # noqa: E402


def get_service(session: AsyncSession = Depends(get_session)) -> SmsService:
    return SmsService(
        order_repo=SmsOrderRepository(session),
        config_repo=SmsPlatformConfigRepository(session),
    )


@app.get("/sms/providers", response_model=ApiResponse)
async def list_providers():
    return ApiResponse(data=ProviderRegistry.list_providers())


@app.get("/sms/providers/{name}/balance", response_model=ApiResponse)
async def get_balance(name: str, service: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        result = await service.get_balance(name)
        return ApiResponse(data=result.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/sms/providers/{name}/prices", response_model=ApiResponse)
async def get_prices(name: str, service: str = "go", svc: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        return ApiResponse(data=await svc.get_prices(name, service))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/sms/providers/{name}/offers", response_model=ApiResponse)
async def get_offers(name: str, service: str = "go", country: str = "", svc: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        return ApiResponse(data=await svc.get_offers(name, service, country))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/sms/number/acquire", response_model=ApiResponse)
async def acquire_number(body: AcquireRequest, service: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        result = await service.acquire_number(body.service, body.country, body.provider, body.max_price, body.fixed_price)
        return ApiResponse(data={"order_id": result.order_id, "phone_number": result.phone_number, "provider": result.provider})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/sms/number/{order_id}/code", response_model=ApiResponse)
async def get_code(order_id: str, timeout: int = 120, service: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        result = await service.get_code(order_id, timeout)
        return ApiResponse(data={"order_id": result.order_id, "code": result.code, "status": result.status.value})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/sms/number/{order_id}/complete", response_model=ApiResponse)
async def complete_order(order_id: str, service: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        await service.complete(order_id)
        return ApiResponse(message="Completed")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/sms/number/{order_id}/cancel", response_model=ApiResponse)
async def cancel_order(order_id: str, service: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        await service.cancel(order_id)
        return ApiResponse(message="Cancelled")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/sms/config", response_model=ApiResponse)
async def get_configs(service: SmsService = Depends(get_service)):
    configs = await service.get_platform_configs()
    return ApiResponse(data=[c.model_dump() for c in configs])


@app.put("/sms/config/{provider_name}", response_model=ApiResponse)
async def save_config(provider_name: str, body: PlatformConfigWrite, service: SmsService = Depends(get_service)):
    result = await service.save_platform_config(
        provider_name=provider_name,
        display_name=body.display_name or provider_name,
        enabled=body.enabled,
        priority=body.priority,
        config=body.config,
    )
    return ApiResponse(data=result.model_dump())
