from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConsumedEvent
from app.repositories.base import BaseRepository


class ConsumedEventRepository(BaseRepository[ConsumedEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ConsumedEvent)

    async def exists(self, *, consumer_group: str, event_id: str) -> bool:
        statement = (
            select(ConsumedEvent.id)
            .where(
                ConsumedEvent.consumer_group == consumer_group,
                ConsumedEvent.event_id == event_id,
            )
            .limit(1)
        )
        return await self.session.scalar(statement) is not None
