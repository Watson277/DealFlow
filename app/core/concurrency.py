import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

ResultT = TypeVar("ResultT")


async def gather_bounded(
    factories: Sequence[Callable[[], Awaitable[ResultT]]],
    *,
    limit: int,
) -> list[ResultT]:
    """Run awaitable factories concurrently while preserving input order."""

    if limit < 1:
        raise ValueError("concurrency limit must be positive")
    semaphore = asyncio.Semaphore(limit)

    async def run(factory: Callable[[], Awaitable[ResultT]]) -> ResultT:
        async with semaphore:
            return await factory()

    tasks = [asyncio.create_task(run(factory)) for factory in factories]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
