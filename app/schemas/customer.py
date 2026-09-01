from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CustomerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
    industry: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=255)
    primary_contact_name: str | None = Field(default=None, max_length=100)
    primary_contact_email: str | None = Field(default=None, max_length=255)
    extra_data: dict[str, Any] = Field(default_factory=dict)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    industry: str | None
    website: str | None
    primary_contact_name: str | None
    primary_contact_email: str | None
    extra_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    offset: int
    limit: int
