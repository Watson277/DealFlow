from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RFP, Proposal, ProposalReview
from app.repositories.base import BaseRepository


class ProposalRepository(BaseRepository[Proposal]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Proposal)

    async def get(self, entity_id: str) -> Proposal | None:
        statement = (
            select(Proposal).join(RFP).where(Proposal.id == entity_id, RFP.deleted_at.is_(None))
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_for_workflow(self, workflow_run_id: str) -> Proposal | None:
        statement = (
            select(Proposal)
            .where(Proposal.workflow_run_id == workflow_run_id)
            .order_by(Proposal.version.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_for_update(self, proposal_id: str) -> Proposal | None:
        statement = (
            select(Proposal)
            .join(RFP)
            .where(Proposal.id == proposal_id, RFP.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_for_rfp(self, rfp_id: str) -> list[Proposal]:
        statement = (
            select(Proposal).where(Proposal.rfp_id == rfp_id).order_by(Proposal.version.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def next_version(self, rfp_id: str) -> int:
        statement = select(func.max(Proposal.version)).where(Proposal.rfp_id == rfp_id)
        latest = await self.session.scalar(statement)
        return int(latest or 0) + 1


class ProposalReviewRepository(BaseRepository[ProposalReview]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ProposalReview)

    async def list_for_proposal(self, proposal_id: str) -> list[ProposalReview]:
        statement = (
            select(ProposalReview)
            .where(ProposalReview.proposal_id == proposal_id)
            .order_by(ProposalReview.created_at)
        )
        return list((await self.session.scalars(statement)).all())
