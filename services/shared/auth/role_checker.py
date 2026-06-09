from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request

from shared.auth.base import AuthResult
from shared.auth.jwt_strategy import JwtAuthStrategy


class RoleChecker:
    """角色权限检查器。根据 JWT token 中的 role 字段判断权限。"""

    ROLE_HIERARCHY = {"admin": 3, "operator": 2, "readonly": 1}

    def __init__(self, jwt_strategy: JwtAuthStrategy):
        self._jwt = jwt_strategy

    def require_role(self, minimum_role: str):
        """FastAPI 依赖注入式权限检查。"""
        min_level = self.ROLE_HIERARCHY.get(minimum_role, 0)

        async def checker(request: Request) -> AuthResult:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing token")
            token = auth_header[7:]
            result = self._jwt.verify(token)
            if not result.authenticated:
                raise HTTPException(status_code=401, detail="Invalid token")
            user_level = self.ROLE_HIERARCHY.get(result.role, 0)
            if user_level < min_level:
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires role '{minimum_role}', got '{result.role}'",
                )
            return result

        return checker

    def check_role(self, role: str, minimum_role: str) -> bool:
        return self.ROLE_HIERARCHY.get(role, 0) >= self.ROLE_HIERARCHY.get(minimum_role, 0)
