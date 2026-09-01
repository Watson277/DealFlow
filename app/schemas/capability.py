from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CapabilityStatus


class CapabilityJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CapabilityStatus
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    customization_notes: str | None = None
    selected_evidence_point_ids: list[str]


class CapabilityEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    qdrant_point_id: str
    page_number: int | None
    snippet: str
    retrieval_score: float | None
    rerank_score: float | None
    rank_position: int


class CapabilityResultResponse(BaseModel):
    id: str
    requirement_id: str
    requirement_key: str
    requirement_text: str
    status: str
    confidence: float | None
    reason: str
    customization_notes: str | None
    model_name: str | None
    prompt_version: str | None
    evidence: list[CapabilityEvidenceResponse]
    created_at: datetime
    updated_at: datetime


class CapabilityResultListResponse(BaseModel):
    items: list[CapabilityResultResponse]
    total: int
