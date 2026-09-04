from fastapi import APIRouter, Depends, HTTPException

from shared.base_schema import ApiResponse
from gateway.schemas import LoginRequest
from gateway.auth_service import AuthService
from gateway.deps import get_auth_service, jwt_strategy

router = APIRouter()


@router.post("/auth/login", response_model=ApiResponse)
async def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    result = await service.login(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return ApiResponse(data=result.model_dump())

