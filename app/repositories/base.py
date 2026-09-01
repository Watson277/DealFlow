from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model_type: type[ModelT]) -> None:
        self.session = session
        self.model_type = model_type

    async def get(self, entity_id: str) -> ModelT | None:
        return await self.session.get(self.model_type, entity_id)

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity
