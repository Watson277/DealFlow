from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CapabilityEvidence, CapabilityResult, Requirement
from app.repositories.base import BaseRepository


class CapabilityResultRepository(BaseRepository[CapabilityResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CapabilityResult)

    async def list_for_rfp(self, rfp_id: str) -> list[CapabilityResult]:
        statement = (
            select(CapabilityResult)
            .join(Requirement, Requirement.id == CapabilityResult.requirement_id)
            .where(Requirement.rfp_id == rfp_id)
            .options(
                selectinload(CapabilityResult.requirement),
                selectinload(CapabilityResult.evidence_items).selectinload(
                    CapabilityEvidence.document
                ),
            )
            .order_by(Requirement.requirement_key)
        )
        return list((await self.session.scalars(statement)).all())


class CapabilityEvidenceRepository(BaseRepository[CapabilityEvidence]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CapabilityEvidence)
