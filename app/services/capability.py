from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RFPNotFoundError
from app.models import CapabilityResult
from app.repositories import CapabilityResultRepository, RFPRepository


class CapabilityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_rfp(self, rfp_id: str) -> list[CapabilityResult]:
        async with self.session.begin():
            rfp = await RFPRepository(self.session).get_active(rfp_id)
            if rfp is None:
                raise RFPNotFoundError(f"RFP {rfp_id} was not found")
            return await CapabilityResultRepository(self.session).list_for_rfp(rfp_id)
