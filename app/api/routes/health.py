from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse, LivenessResponse
from app.services.health import HealthService, get_health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    return LivenessResponse(
        status="healthy",
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def readiness(
    response: Response,
    health_service: Annotated[HealthService, Depends(get_health_service)],
) -> HealthResponse:
    result = await health_service.check_all()
    if result.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
