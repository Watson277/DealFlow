from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=64)
    requirement_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    mandatory: bool
    source_page_start: int | None = Field(default=None, ge=1)
    source_page_end: int | None = Field(default=None, ge=1)
    source_quote: str | None = None
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> "ExtractedRequirement":
        if (
            self.source_page_start is not None
            and self.source_page_end is not None
            and self.source_page_end < self.source_page_start
        ):
            raise ValueError("source_page_end must not precede source_page_start")
        return self


class RequirementExtractionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[ExtractedRequirement]


class RequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rfp_id: str
    source_document_id: str
    requirement_key: str
    category: str
    requirement_text: str
    normalized_text: str
    mandatory: bool
    source_page_start: int | None
    source_page_end: int | None
    source_quote: str | None
    confidence: float | None
    fingerprint: str | None
    created_at: datetime
    updated_at: datetime


class RequirementListResponse(BaseModel):
    items: list[RequirementResponse]
    total: int
