from datetime import timedelta
from typing import Any, Literal, TypeAlias, cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.infrastructure.messaging.kafka import KafkaProducerService
from app.models import OutboxEvent
from app.models.enums import OutboxStatus
from app.models.mixins import utc_now
from app.repositories.outbox import OutboxEventRepository

logger = structlog.get_logger(__name__)
EventDeliveryStatus: TypeAlias = Literal["PENDING", "PUBLISHED", "FAILED"]


class OutboxPublisher:
    def __init__(self, kafka: KafkaProducerService, settings: Settings | None = None) -> None:
        self.kafka = kafka
        self.settings = settings or kafka.settings

    async def publish_event(
        self,
        session: AsyncSession,
        event: OutboxEvent,
    ) -> EventDeliveryStatus:
        try:
            async with session.begin():
                repository = OutboxEventRepository(session)
                persisted_event = await repository.get_for_update(event.id)
                if persisted_event is None:
                    logger.warning("outbox_event_missing", event_id=event.id)
                    return "PENDING"
                if persisted_event.status != OutboxStatus.PENDING.value:
                    return self._delivery_status(persisted_event.status)
                if (
                    persisted_event.attempts > 0
                    and persisted_event.available_at > utc_now()
                ):
                    return "PENDING"
                return await self.publish_claimed_event(repository, persisted_event)
        except Exception as exc:
            logger.warning(
                "outbox_publish_transaction_failed",
                event_id=event.id,
                error_type=type(exc).__name__,
            )
            return "PENDING"

    async def publish_claimed_event(
        self,
        repository: OutboxEventRepository,
        event: OutboxEvent,
    ) -> EventDeliveryStatus:
        """Publish an event whose row is locked by the caller's DB transaction."""
        payload: dict[str, Any] = dict(event.payload)
        try:
            await self.kafka.publish(
                topic=event.topic,
                event_key=event.event_key,
                payload=payload,
            )
        except Exception as exc:
            logger.warning(
                "outbox_publish_failed",
                event_id=event.id,
                topic=event.topic,
                error_type=type(exc).__name__,
            )
            failed_at = utc_now()
            delay_seconds = self.retry_delay_seconds(event.attempts)
            repository.record_failure(
                event,
                type(exc).__name__,
                available_at=failed_at + timedelta(seconds=delay_seconds),
            )
            logger.info(
                "outbox_event_rescheduled",
                event_id=event.id,
                topic=event.topic,
                attempts=event.attempts,
                retry_in_seconds=delay_seconds,
            )
            return "PENDING"

        repository.mark_published(event, utc_now())
        return "PUBLISHED"

    def retry_delay_seconds(self, attempts: int) -> float:
        exponent = min(max(attempts, 0), 30)
        delay = self.settings.outbox_relay_initial_backoff_seconds * (2**exponent)
        return float(min(delay, self.settings.outbox_relay_max_backoff_seconds))

    @staticmethod
    def _delivery_status(status: str) -> EventDeliveryStatus:
        if status in {
            OutboxStatus.PENDING.value,
            OutboxStatus.PUBLISHED.value,
            OutboxStatus.FAILED.value,
        }:
            return cast(EventDeliveryStatus, status)
        logger.warning("outbox_unknown_status", status=status)
        return "PENDING"
