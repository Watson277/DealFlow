import asyncio
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

import redis.asyncio as redis
import structlog
from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]
from minio import Minio
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import engine
from app.schemas.health import HealthResponse, HealthStatus, ServiceHealth

logger = structlog.get_logger(__name__)
HealthCheck = Callable[[], Awaitable[None]]


class HealthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def check_all(self) -> HealthResponse:
        checks: dict[str, HealthCheck] = {
            "mysql": self._check_mysql,
            "redis": self._check_redis,
            "kafka": self._check_kafka,
            "qdrant": self._check_qdrant,
            "minio": self._check_minio,
        }
        results = await asyncio.gather(
            *(self._run_check(name, check) for name, check in checks.items())
        )
        service_results = dict(zip(checks, results, strict=True))
        overall_status: HealthStatus = (
            "healthy"
            if all(result.status == "healthy" for result in service_results.values())
            else "unhealthy"
        )
        return HealthResponse(
            status=overall_status,
            application=self.settings.app_name,
            version=self.settings.app_version,
            environment=self.settings.app_env,
            checks=service_results,
        )

    async def _run_check(self, name: str, check: HealthCheck) -> ServiceHealth:
        started = time.perf_counter()
        try:
            await asyncio.wait_for(check(), timeout=self.settings.healthcheck_timeout_seconds)
        except Exception as exc:
            logger.warning(
                "dependency_healthcheck_failed",
                service=name,
                error_type=type(exc).__name__,
            )
            return ServiceHealth(
                status="unhealthy",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail=f"connection failed ({type(exc).__name__})",
            )
        return ServiceHealth(
            status="healthy",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail="reachable",
        )

    async def _check_mysql(self) -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def _check_redis(self) -> None:
        client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
        try:
            if not await client.ping():
                raise RuntimeError("Redis did not respond with PONG")
        finally:
            await client.aclose()

    async def _check_kafka(self) -> None:
        producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            request_timeout_ms=int(self.settings.healthcheck_timeout_seconds * 1000),
        )
        started = False
        try:
            await producer.start()
            started = True
        finally:
            if started:
                await producer.stop()

    async def _check_qdrant(self) -> None:
        client = AsyncQdrantClient(url=self.settings.qdrant_url)
        try:
            await client.get_collections()
        finally:
            await client.close()

    async def _check_minio(self) -> None:
        client = Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )
        bucket_exists = await asyncio.to_thread(
            client.bucket_exists,
            self.settings.minio_bucket,
        )
        if not bucket_exists:
            raise RuntimeError("MinIO bucket does not exist")


@lru_cache
def get_health_service() -> HealthService:
    return HealthService(get_settings())
