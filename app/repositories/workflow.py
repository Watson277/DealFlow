from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkflowRun
from app.repositories.base import BaseRepository


class WorkflowRunRepository(BaseRepository[WorkflowRun]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WorkflowRun)

    async def get_latest_for_rfp(self, rfp_id: str) -> WorkflowRun | None:
        statement = (
            select(WorkflowRun)
            .where(WorkflowRun.rfp_id == rfp_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
