import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

import redis.asyncio as redis
import structlog

from app.core.config import Settings
from app.core.exceptions import LockNotAcquiredError, LockOwnershipLostError

logger = structlog.get_logger(__name__)

RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

RENEW_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
"""


class DistributedLockService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    @asynccontextmanager
    async def lock(self, key: str, *, ttl_seconds: int | None = None) -> AsyncIterator[None]:
        token = uuid4().hex
        ttl = ttl_seconds or self.settings.rfp_lock_ttl_seconds
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.rfp_lock_acquire_timeout_seconds

        while True:
            acquired = await self.client.set(
                key,
                token,
                nx=True,
                ex=ttl,
            )
            if acquired:
                break
            if loop.time() >= deadline:
                raise LockNotAcquiredError(f"could not acquire lock {key}")
            await asyncio.sleep(0.25)

        owner_task = asyncio.current_task()
        if owner_task is None:
            await self._release(key, token)
            raise RuntimeError("distributed lock must be used from an asyncio task")

        lock_lost = asyncio.Event()
        watchdog: asyncio.Task[None] | None = None
        if self.settings.redis_lock_watchdog_enabled:
            watchdog = asyncio.create_task(
                self._watch_lock(
                    key=key,
                    token=token,
                    ttl_seconds=ttl,
                    owner_task=owner_task,
                    lock_lost=lock_lost,
                ),
                name=f"redis-lock-watchdog:{key}",
            )

        try:
            try:
                yield
            except asyncio.CancelledError as exc:
                if lock_lost.is_set():
                    raise LockOwnershipLostError(f"lost ownership of lock {key}") from exc
                raise
            if lock_lost.is_set():
                raise LockOwnershipLostError(f"lost ownership of lock {key}")
        finally:
            if watchdog is not None:
                watchdog.cancel()
                with suppress(asyncio.CancelledError):
                    await watchdog
            await self._release(key, token)

    async def _watch_lock(
        self,
        *,
        key: str,
        token: str,
        ttl_seconds: int,
        owner_task: asyncio.Task[object],
        lock_lost: asyncio.Event,
    ) -> None:
        loop = asyncio.get_running_loop()
        interval = min(
            self.settings.redis_lock_watchdog_interval_seconds,
            ttl_seconds / 3,
        )
        retry_interval = min(1.0, interval)
        lease_deadline = loop.time() + ttl_seconds
        delay = interval
        renewal_error_reported = False

        while True:
            await asyncio.sleep(delay)
            try:
                renewed = await self.client.eval(
                    RENEW_LOCK_SCRIPT,
                    1,
                    key,
                    token,
                    ttl_seconds,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                remaining = lease_deadline - loop.time()
                if not renewal_error_reported:
                    logger.warning(
                        "redis_lock_watchdog_renewal_failed",
                        key=key,
                        error_type=type(exc).__name__,
                    )
                    renewal_error_reported = True
                if remaining <= 0:
                    self._mark_lock_lost(key, owner_task, lock_lost)
                    return
                delay = min(retry_interval, remaining)
                continue

            if renewed != 1:
                self._mark_lock_lost(key, owner_task, lock_lost)
                return

            if renewal_error_reported:
                logger.info("redis_lock_watchdog_recovered", key=key)
                renewal_error_reported = False
            lease_deadline = loop.time() + ttl_seconds
            delay = interval

    @staticmethod
    def _mark_lock_lost(
        key: str,
        owner_task: asyncio.Task[object],
        lock_lost: asyncio.Event,
    ) -> None:
        logger.error("redis_lock_ownership_lost", key=key)
        lock_lost.set()
        owner_task.cancel()

    async def _release(self, key: str, token: str) -> None:
        try:
            await self.client.eval(RELEASE_LOCK_SCRIPT, 1, key, token)
        except Exception as exc:
            logger.warning(
                "redis_lock_release_failed",
                key=key,
                error_type=type(exc).__name__,
            )

    async def close(self) -> None:
        await self.client.aclose()
