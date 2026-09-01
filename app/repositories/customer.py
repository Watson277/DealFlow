from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Customer)

    async def get_active(self, customer_id: str) -> Customer | None:
        statement = select(Customer).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None),
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Customer | None:
        statement = select(Customer).where(
            Customer.code == code,
            Customer.deleted_at.is_(None),
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active_for_update(self, customer_id: str) -> Customer | None:
        statement = (
            select(Customer)
            .where(Customer.id == customer_id, Customer.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_active(
        self,
        *,
        offset: int,
        limit: int,
        search: str | None = None,
    ) -> list[Customer]:
        statement = select(Customer).where(Customer.deleted_at.is_(None))
        if search:
            statement = statement.where(
                or_(
                    Customer.name.contains(search, autoescape=True),
                    Customer.code.contains(search, autoescape=True),
                )
            )
        statement = statement.order_by(Customer.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def count_active(self, *, search: str | None = None) -> int:
        statement = select(func.count()).select_from(Customer).where(Customer.deleted_at.is_(None))
        if search:
            statement = statement.where(
                or_(
                    Customer.name.contains(search, autoescape=True),
                    Customer.code.contains(search, autoescape=True),
                )
            )
        return int((await self.session.scalar(statement)) or 0)
