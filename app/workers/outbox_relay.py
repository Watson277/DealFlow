import asyncio
from contextlib import suppress
from dataclasses import dataclass

import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import async_session_factory, close_database
from app.infrastructure.messaging.kafka import KafkaProducerService
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.models.mixins import utc_now
from app.repositories.outbox import OutboxEventRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RelayBatchResult:
    selected: int
    published: int
    rescheduled: int


class OutboxRelay:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.kafka = KafkaProducerService(self.settings)
        self.publisher = OutboxPublisher(self.kafka, self.settings)
        self._stop_requested = asyncio.Event()

    async def run(self) -> None:
        logger.info(
            "outbox_relay_started",
            batch_size=self.settings.outbox_relay_batch_size,
            poll_interval_seconds=self.settings.outbox_relay_poll_interval_seconds,
        )
        try:
            while not self._stop_requested.is_set():
                try:
                    result = await self.relay_once()
                except Exception:
                    logger.exception("outbox_relay_batch_failed")
                    await self._wait_for_next_poll()
                    continue

                if result.selected:
                    logger.info(
                        "outbox_relay_batch_completed",
                        selected=result.selected,
                        published=result.published,
                        rescheduled=result.rescheduled,
                    )
                    continue
                await self._wait_for_next_poll()
        finally:
            await self.close()

    async def relay_once(self) -> RelayBatchResult:
        published = 0
        rescheduled = 0
        async with async_session_factory() as session, session.begin():
            repository = OutboxEventRepository(session)
            events = await repository.list_pending(
                available_before=utc_now(),
                limit=self.settings.outbox_relay_batch_size,
            )
            for event in events:
                status = await self.publisher.publish_claimed_event(repository, event)
                if status == "PUBLISHED":
                    published += 1
                else:
                    rescheduled += 1

        return RelayBatchResult(
            selected=len(events),
            published=published,
            rescheduled=rescheduled,
        )

    def request_stop(self) -> None:
        self._stop_requested.set()

    async def close(self) -> None:
        await self.kafka.stop()
        await close_database()
        logger.info("outbox_relay_stopped")

    async def _wait_for_next_poll(self) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(
                self._stop_requested.wait(),
                timeout=self.settings.outbox_relay_poll_interval_seconds,
            )


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    relay = OutboxRelay(settings)
    await relay.run()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
