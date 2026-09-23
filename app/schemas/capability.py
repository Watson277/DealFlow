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


class CapabilityBatchJudgmentItem(CapabilityJudgment):
    requirement_key: str = Field(min_length=1, max_length=32)


class CapabilityBatchJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judgments: list[CapabilityBatchJudgmentItem] = Field(min_length=1, max_length=8)


class CapabilityEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    qdrant_point_id: str
    document_title: str | None
    document_version: str | None
    category: str | None
    parent_id: str | None
    child_chunk_id: str | None
    page_number: int | None
    page_end: int | None
    snippet: str
    matched_child_text: str | None
    section_path: list[str] | None
    block_types: list[str] | None
    source_block_ids: list[str] | None
    source_type: str | None
    source_location: dict[str, object] | None
    retrieval_mode: str | None
    retrieval_score: float | None
    rerank_score: float | None
    rank_position: int
    is_selected: bool
    selection_order: int | None


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
    citation_audit: dict[str, object]
    evidence: list[CapabilityEvidenceResponse]
    created_at: datetime
    updated_at: datetime


class CapabilityResultListResponse(BaseModel):
    items: list[CapabilityResultResponse]
    total: int
