from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_customer_service
from app.core.exceptions import (
    CustomerCodeConflictError,
    CustomerNotFoundError,
    DeletionConflictError,
)
from app.schemas.customer import CustomerCreate, CustomerListResponse, CustomerResponse
from app.services.customer import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    service: Annotated[CustomerService, Depends(get_customer_service)],
) -> Response:
    try:
        await service.delete(str(customer_id))
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeletionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    data: CustomerCreate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
) -> CustomerResponse:
    try:
        customer = await service.create(data)
    except CustomerCodeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CustomerResponse.model_validate(customer)


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    service: Annotated[CustomerService, Depends(get_customer_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> CustomerListResponse:
    page = await service.list(offset=offset, limit=limit, search=search)
    return CustomerListResponse(
        items=[CustomerResponse.model_validate(item) for item in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    service: Annotated[CustomerService, Depends(get_customer_service)],
) -> CustomerResponse:
    try:
        customer = await service.get(str(customer_id))
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CustomerResponse.model_validate(customer)
