from fastapi import APIRouter, HTTPException

from shared.base_schema import ApiResponse
from config_service.schemas import ConfigWrite

router = APIRouter(prefix="/config", tags=["config"])


def _get_service():
    """占位：实际会在 main.py 中通过依赖注入提供。"""
    raise NotImplementedError("Use dependency injection")
