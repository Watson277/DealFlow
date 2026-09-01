from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ProposalNotFoundError, RFPNotFoundError
from app.models import Proposal
from app.repositories import ProposalRepository, RFPRepository
from app.services.storage import ObjectStorageService


class ProposalService:
    def __init__(self, session: AsyncSession, storage: ObjectStorageService) -> None:
        self.session = session
        self.storage = storage

    async def get(self, proposal_id: str) -> Proposal:
        async with self.session.begin():
            proposal = await ProposalRepository(self.session).get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(f"proposal {proposal_id} was not found")
        return proposal

    async def list_for_rfp(self, rfp_id: str) -> list[Proposal]:
        async with self.session.begin():
            rfp = await RFPRepository(self.session).get_active(rfp_id)
            if rfp is None:
                raise RFPNotFoundError(f"RFP {rfp_id} was not found")
            return await ProposalRepository(self.session).list_for_rfp(rfp_id)

    async def get_markdown(self, proposal_id: str) -> str:
        proposal = await self.get(proposal_id)
        if not proposal.markdown_object_key:
            raise ProposalNotFoundError(f"proposal {proposal_id} has no Markdown artifact")
        content = await self.storage.download(
            self.storage.settings.minio_bucket,
            proposal.markdown_object_key,
        )
        return content.decode("utf-8")
