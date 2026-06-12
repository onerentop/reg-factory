from fastapi import APIRouter, Depends, HTTPException

from shared.base_schema import ApiResponse
from shared.auth import RoleChecker, AuthResult
from gateway.schemas import LoginRequest, UserCreate, ApiKeyCreate
from gateway.auth_service import AuthService
from gateway.deps import get_auth_service, jwt_strategy

router = APIRouter()
role_checker = RoleChecker(jwt_strategy)


@router.post("/auth/login", response_model=ApiResponse)
async def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    result = await service.login(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return ApiResponse(data=result.model_dump())


@router.post("/auth/users", response_model=ApiResponse)
async def create_user(body: UserCreate, service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    user = await service.create_user(body.username, body.password, body.role)
    from shared.audit import AuditRecorder
    recorder = AuditRecorder()
    recorder.record(operator="system", action="create_user", target=body.username)
    return ApiResponse(data=user.model_dump())


@router.get("/auth/users", response_model=ApiResponse)
async def list_users(service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    users = await service.list_users()
    return ApiResponse(data=[u.model_dump() for u in users])


@router.post("/auth/api-keys", response_model=ApiResponse)
async def create_api_key(body: ApiKeyCreate, service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    key = await service.create_api_key(body.name, "system", body.scopes)
    return ApiResponse(data=key.model_dump())


@router.get("/auth/api-keys", response_model=ApiResponse)
async def list_api_keys(owner_id: str = "system", service: AuthService = Depends(get_auth_service)):
    keys = await service.list_api_keys(owner_id)
    return ApiResponse(data=[k.model_dump() for k in keys])


@router.delete("/auth/api-keys/{key_id}", response_model=ApiResponse)
async def revoke_api_key(key_id: str, service: AuthService = Depends(get_auth_service), _auth: AuthResult = Depends(role_checker.require_role("admin"))):
    revoked = await service.revoke_api_key(key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    from shared.audit import AuditRecorder
    recorder = AuditRecorder()
    recorder.record(operator="system", action="revoke_api_key", target=key_id)
    return ApiResponse(message="API key revoked")
