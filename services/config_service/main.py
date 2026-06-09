import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import DatabaseManager
from shared.base_schema import ApiResponse
from config_service.schemas import ConfigWrite
from config_service.repository import ConfigRepository, ConfigVersionRepository
from config_service.service import ConfigService


db = DatabaseManager(
    url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///regfactory_dev.db")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = db.engine
    yield
    await db.close()


app = FastAPI(title="RegFactory Config Service", version="0.1.0", lifespan=lifespan)


async def get_session():
    async with db.get_session() as session:
        yield session


def get_service(session: AsyncSession = Depends(get_session)) -> ConfigService:
    repo = ConfigRepository(session)
    version_repo = ConfigVersionRepository(session)
    return ConfigService(repo, version_repo)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "config_service"}


@app.get("/config/", response_model=ApiResponse)
async def list_configs(
    category: str | None = None,
    service: ConfigService = Depends(get_service),
):
    if category:
        items = await service.get_by_category(category)
    else:
        items = await service.get_all()
    return ApiResponse(data=[item.model_dump() for item in items])


@app.get("/config/{key:path}", response_model=ApiResponse)
async def get_config(key: str, service: ConfigService = Depends(get_service)):
    entry = await service.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Config '{key}' not found")
    return ApiResponse(data=entry.model_dump())


@app.put("/config/{key:path}", response_model=ApiResponse)
async def set_config(
    key: str, body: ConfigWrite, service: ConfigService = Depends(get_service)
):
    entry = await service.set(key, body.value, body.category)
    return ApiResponse(data=entry.model_dump())


@app.delete("/config/{key:path}", response_model=ApiResponse)
async def delete_config(key: str, service: ConfigService = Depends(get_service)):
    deleted = await service.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Config '{key}' not found")
    return ApiResponse(message="Deleted")


@app.get("/config/{key:path}/history", response_model=ApiResponse)
async def get_history(key: str, service: ConfigService = Depends(get_service)):
    versions = await service.get_history(key)
    return ApiResponse(data=[v.model_dump() for v in versions])
