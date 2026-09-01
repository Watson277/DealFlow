from typing import Any, Literal, TypeAlias

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent
from app.models.mixins import utc_now
from app.repositories.outbox import OutboxEventRepository
from app.services.kafka import KafkaProducerService

logger = structlog.get_logger(__name__)
EventDeliveryStatus: TypeAlias = Literal["PENDING", "PUBLISHED", "FAILED"]


class OutboxPublisher:
    def __init__(self, kafka: KafkaProducerService) -> None:
        self.kafka = kafka

    async def publish_event(
        self,
        session: AsyncSession,
        event: OutboxEvent,
    ) -> EventDeliveryStatus:
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
            await self._record_failure(session, event.id, type(exc).__name__)
            return "PENDING"

        try:
            async with session.begin():
                repository = OutboxEventRepository(session)
                persisted_event = await repository.get(event.id)
                if persisted_event is None:
                    raise RuntimeError("outbox event disappeared after commit")
                repository.mark_published(persisted_event, utc_now())
        except Exception as exc:
            logger.warning(
                "outbox_publish_state_update_failed",
                event_id=event.id,
                error_type=type(exc).__name__,
            )
            return "PENDING"
        return "PUBLISHED"

    @staticmethod
    async def _record_failure(session: AsyncSession, event_id: str, error_type: str) -> None:
        try:
            async with session.begin():
                repository = OutboxEventRepository(session)
                event = await repository.get(event_id)
                if event is not None:
                    repository.record_failure(event, error_type)
        except Exception:
            logger.exception("outbox_failure_state_update_failed", event_id=event_id)
