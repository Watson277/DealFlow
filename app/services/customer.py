from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    CustomerCodeConflictError,
    CustomerNotFoundError,
    DeletionConflictError,
)
from app.models import RFP, Customer
from app.models.mixins import generate_uuid, utc_now
from app.repositories import CustomerRepository
from app.schemas.customer import CustomerCreate


@dataclass(frozen=True, slots=True)
class CustomerPage:
    items: list[Customer]
    total: int
    offset: int
    limit: int


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: CustomerCreate) -> Customer:
        normalized_code = data.code.upper()
        repository = CustomerRepository(self.session)
        customer = Customer(
            id=generate_uuid(),
            name=data.name,
            code=normalized_code,
            industry=data.industry,
            website=data.website,
            primary_contact_name=data.primary_contact_name,
            primary_contact_email=data.primary_contact_email,
            extra_data=data.extra_data,
        )

        try:
            async with self.session.begin():
                if await repository.get_by_code(normalized_code) is not None:
                    raise CustomerCodeConflictError(
                        f"customer code {normalized_code} already exists"
                    )
                repository.add(customer)
                await self.session.flush()
        except IntegrityError as exc:
            raise CustomerCodeConflictError(
                f"customer code {normalized_code} already exists"
            ) from exc
        return customer

    async def get(self, customer_id: str) -> Customer:
        async with self.session.begin():
            customer = await CustomerRepository(self.session).get_active(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"customer {customer_id} was not found")
        return customer

    async def delete(self, customer_id: str) -> None:
        async with self.session.begin():
            customer = await CustomerRepository(self.session).get_active_for_update(customer_id)
            if customer is None:
                raise CustomerNotFoundError("客户不存在或已删除")
            linked_rfp = await self.session.scalar(
                select(RFP.id)
                .where(RFP.customer_id == customer_id, RFP.deleted_at.is_(None))
                .limit(1)
                .with_for_update()
            )
            if linked_rfp is not None:
                raise DeletionConflictError("该客户仍有关联任务，请先删除其全部 RFP 任务")
            customer.deleted_at = utc_now()

    async def list(
        self,
        *,
        offset: int,
        limit: int,
        search: str | None,
    ) -> CustomerPage:
        normalized_search = search.strip() if search else None
        repository = CustomerRepository(self.session)
        async with self.session.begin():
            items = await repository.list_active(
                offset=offset,
                limit=limit,
                search=normalized_search,
            )
            total = await repository.count_active(search=normalized_search)
        return CustomerPage(items=items, total=total, offset=offset, limit=limit)
