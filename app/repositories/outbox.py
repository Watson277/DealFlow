from datetime import datetime
from typing import cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent
from app.models.enums import OutboxStatus
from app.repositories.base import BaseRepository


class OutboxEventRepository(BaseRepository[OutboxEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OutboxEvent)

    async def get_for_update(self, event_id: str) -> OutboxEvent | None:
        statement: Select[tuple[OutboxEvent]] = (
            select(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return cast(OutboxEvent | None, await self.session.scalar(statement))

    async def list_pending(
        self,
        *,
        available_before: datetime,
        limit: int = 100,
    ) -> list[OutboxEvent]:
        statement: Select[tuple[OutboxEvent]] = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == OutboxStatus.PENDING.value,
                OutboxEvent.available_at <= available_before,
            )
            .order_by(OutboxEvent.available_at, OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(statement)).all())

    def mark_published(self, event: OutboxEvent, published_at: datetime) -> None:
        event.status = OutboxStatus.PUBLISHED.value
        event.published_at = published_at
        event.last_error = None

    def record_failure(
        self,
        event: OutboxEvent,
        error_type: str,
        *,
        available_at: datetime,
    ) -> None:
        event.status = OutboxStatus.PENDING.value
        event.attempts += 1
        event.available_at = available_at
        event.last_error = error_type[:1000]
