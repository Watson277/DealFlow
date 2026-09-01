from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Requirement
from app.repositories.base import BaseRepository


class RequirementRepository(BaseRepository[Requirement]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Requirement)

    async def list_for_rfp(self, rfp_id: str) -> list[Requirement]:
        statement = (
            select(Requirement)
            .where(Requirement.rfp_id == rfp_id)
            .order_by(Requirement.requirement_key)
        )
        return list((await self.session.scalars(statement)).all())

    async def count_for_rfp(self, rfp_id: str) -> int:
        statement = (
            select(func.count()).select_from(Requirement).where(Requirement.rfp_id == rfp_id)
        )
        return int((await self.session.scalar(statement)) or 0)
