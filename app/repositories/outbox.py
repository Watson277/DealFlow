from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent
from app.models.enums import OutboxStatus
from app.repositories.base import BaseRepository


class OutboxEventRepository(BaseRepository[OutboxEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OutboxEvent)

    async def list_pending(self, *, limit: int = 100) -> list[OutboxEvent]:
        statement: Select[tuple[OutboxEvent]] = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING.value)
            .order_by(OutboxEvent.available_at, OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(statement)).all())

    def mark_published(self, event: OutboxEvent, published_at: datetime) -> None:
        event.status = OutboxStatus.PUBLISHED.value
        event.published_at = published_at
        event.last_error = None

    def record_failure(self, event: OutboxEvent, error_type: str) -> None:
        event.status = OutboxStatus.PENDING.value
        event.attempts += 1
        event.last_error = error_type[:1000]
