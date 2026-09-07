import structlog
from sqlalchemy.exc import IntegrityError

from app.db.session import async_session_factory
from app.models import ConsumedEvent
from app.models.mixins import generate_uuid
from app.repositories import ConsumedEventRepository

logger = structlog.get_logger(__name__)


class ConsumedEventTracker:
    def __init__(self, consumer_group: str) -> None:
        self.consumer_group = consumer_group

    async def is_consumed(self, event_id: str) -> bool:
        async with async_session_factory() as session, session.begin():
            return await ConsumedEventRepository(session).exists(
                consumer_group=self.consumer_group,
                event_id=event_id,
            )

    async def record(
        self,
        *,
        event_id: str,
        event_type: str,
        topic: str,
        partition: int,
        offset: int,
    ) -> bool:
        consumed_event = ConsumedEvent(
            id=generate_uuid(),
            consumer_group=self.consumer_group,
            event_id=event_id,
            event_type=event_type,
            topic=topic,
            partition=partition,
            offset=offset,
        )
        try:
            async with async_session_factory() as session, session.begin():
                ConsumedEventRepository(session).add(consumed_event)
                await session.flush()
        except IntegrityError:
            logger.info(
                "consumed_event_already_recorded",
                consumer_group=self.consumer_group,
                event_id=event_id,
            )
            return False
        return True
