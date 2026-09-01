from typing import Literal

from pydantic import BaseModel

HealthStatus = Literal["healthy", "unhealthy"]


class ServiceHealth(BaseModel):
    status: HealthStatus
    latency_ms: float
    detail: str


class LivenessResponse(BaseModel):
    status: Literal["healthy"]
    application: str
    version: str
    environment: str


class HealthResponse(BaseModel):
    status: HealthStatus
    application: str
    version: str
    environment: str
    checks: dict[str, ServiceHealth]
