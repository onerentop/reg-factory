import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import DatabaseManager
from shared.log_handler import setup_logger
from shared.base_schema import ApiResponse, PaginatedResponse
from account_service.schemas import (
    AccountCreate, AccountUpdate, StepUpdate,
    BatchDeleteRequest, BatchExportRequest, BatchRetryRequest, ImportRequest,
)
from account_service.service import AccountService
from account_service.repository import AccountRepository, StepRepository

db = DatabaseManager(
    url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///regfactory_dev.db")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = db.engine
    from shared.base_model import BaseModel
    from account_service.models import Account, RegistrationStep
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    logger = setup_logger("account_service")
    logger.info("Account Service starting")
    yield
    await db.close()


app = FastAPI(title="RegFactory Account Service", version="0.1.0", lifespan=lifespan)
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


def get_service(session: AsyncSession = Depends(get_session)) -> AccountService:
    return AccountService(
        account_repo=AccountRepository(session),
        step_repo=StepRepository(session),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "account_service"}


@app.get("/accounts", response_model=ApiResponse)
async def list_accounts(
    platform: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: AccountService = Depends(get_service),
):
    accounts, total = await service.list_accounts(platform, status, keyword, page, page_size)
    return ApiResponse(data={
        "items": [a.model_dump() for a in accounts],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@app.get("/accounts/{account_id}", response_model=ApiResponse)
async def get_account(account_id: str, service: AccountService = Depends(get_service)):
    account = await service.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return ApiResponse(data=account.model_dump())


@app.post("/accounts", response_model=ApiResponse)
async def create_account(body: AccountCreate, service: AccountService = Depends(get_service)):
    account = await service.create_account(body)
    return ApiResponse(data=account.model_dump())


@app.put("/accounts/{account_id}", response_model=ApiResponse)
async def update_account(account_id: str, body: AccountUpdate, service: AccountService = Depends(get_service)):
    account = await service.update_account(account_id, body)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return ApiResponse(data=account.model_dump())


@app.delete("/accounts/{account_id}", response_model=ApiResponse)
async def delete_account(account_id: str, service: AccountService = Depends(get_service)):
    deleted = await service.delete_account(account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Account not found")
    return ApiResponse(message="Deleted")


@app.post("/accounts/batch/delete", response_model=ApiResponse)
async def batch_delete(body: BatchDeleteRequest, service: AccountService = Depends(get_service)):
    count = await service.delete_batch(body.account_ids)
    return ApiResponse(data={"deleted": count})


@app.post("/accounts/batch/export", response_model=ApiResponse)
async def batch_export(body: BatchExportRequest, service: AccountService = Depends(get_service)):
    content = await service.export_accounts(
        body.format, body.account_ids or None, body.platform, body.status,
    )
    return ApiResponse(data={"content": content, "format": body.format})


@app.post("/accounts/batch/retry", response_model=ApiResponse)
async def batch_retry(body: BatchRetryRequest, service: AccountService = Depends(get_service)):
    return ApiResponse(data={"queued": len(body.account_ids), "message": "Retry tasks queued"})


@app.get("/accounts/{account_id}/steps", response_model=ApiResponse)
async def get_steps(account_id: str, service: AccountService = Depends(get_service)):
    steps = await service.get_steps(account_id)
    return ApiResponse(data=[s.model_dump() for s in steps])


@app.put("/accounts/{account_id}/steps/{step_number}", response_model=ApiResponse)
async def update_step(
    account_id: str, step_number: int, body: StepUpdate,
    service: AccountService = Depends(get_service),
):
    updated = await service.update_step(account_id, step_number, body)
    if not updated:
        raise HTTPException(status_code=404, detail="Step not found")
    return ApiResponse(message="Step updated")


@app.post("/accounts/import", response_model=ApiResponse)
async def import_accounts(body: ImportRequest, service: AccountService = Depends(get_service)):
    count = await service.import_accounts(body.content, body.format, body.platform)
    return ApiResponse(data={"imported": count})
