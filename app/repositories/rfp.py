from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models import RFP
from app.repositories.base import BaseRepository


class RFPRepository(BaseRepository[RFP]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RFP)

    async def get_active(self, rfp_id: str) -> RFP | None:
        statement = select(RFP).where(RFP.id == rfp_id, RFP.deleted_at.is_(None))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active_for_update(self, rfp_id: str) -> RFP | None:
        statement = (
            select(RFP)
            .where(RFP.id == rfp_id, RFP.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_detail(self, rfp_id: str) -> RFP | None:
        statement = (
            select(RFP)
            .where(RFP.id == rfp_id, RFP.deleted_at.is_(None))
            .options(
                selectinload(RFP.documents),
                selectinload(RFP.workflow_runs),
            )
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_active(
        self,
        *,
        offset: int,
        limit: int,
        customer_id: str | None,
        status: str | None,
        search: str | None,
    ) -> list[RFP]:
        statement = select(RFP).where(RFP.deleted_at.is_(None))
        statement = statement.where(*self._build_filters(customer_id, status, search))
        statement = statement.order_by(RFP.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def count_active(
        self,
        *,
        customer_id: str | None,
        status: str | None,
        search: str | None,
    ) -> int:
        statement = select(func.count()).select_from(RFP).where(RFP.deleted_at.is_(None))
        statement = statement.where(*self._build_filters(customer_id, status, search))
        return int((await self.session.scalar(statement)) or 0)

    @staticmethod
    def _build_filters(
        customer_id: str | None,
        status: str | None,
        search: str | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if customer_id:
            filters.append(RFP.customer_id == customer_id)
        if status:
            filters.append(RFP.status == status)
        if search:
            filters.append(
                or_(
                    RFP.title.contains(search, autoescape=True),
                    RFP.reference_number.contains(search, autoescape=True),
                )
            )
        return filters
