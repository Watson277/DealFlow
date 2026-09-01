import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import redis.asyncio as redis

from app.core.config import Settings
from app.core.exceptions import LockNotAcquiredError

RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
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

        try:
            yield
        finally:
            await self.client.eval(RELEASE_LOCK_SCRIPT, 1, key, token)

    async def close(self) -> None:
        await self.client.aclose()
