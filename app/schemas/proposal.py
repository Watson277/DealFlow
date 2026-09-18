from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CapabilityStatus, ReviewDecision


class ProposalRequirementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_key: str = Field(min_length=1, max_length=32)
    requirement: str = Field(min_length=1)
    capability_status: CapabilityStatus
    response: str = Field(min_length=1)
    evidence_summary: str = Field(min_length=1)
    risk_or_gap: str | None = None


class ProposalSections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    executive_summary: str = Field(min_length=1)
    technical_solution: str = Field(min_length=1)
    security_compliance: str = Field(min_length=1)
    sla: str = Field(min_length=1)
    deployment: str = Field(min_length=1)
    risks_and_gaps: str = Field(min_length=1)
    commercial_notes: str = Field(min_length=1)


class ProposalDraft(ProposalSections):
    requirement_responses: list[ProposalRequirementResponse]


class ProposalBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_key: str = Field(min_length=1, max_length=32)
    response: str = Field(min_length=1, max_length=800)
    evidence_summary: str = Field(min_length=1, max_length=400)
    risk_or_gap: str | None = Field(default=None, max_length=600)


class ProposalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_responses: list[ProposalBatchItem]


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rfp_id: str
    workflow_run_id: str
    version: int
    status: str
    title: str
    executive_summary: str | None
    markdown_object_key: str | None
    model_name: str | None
    prompt_version: str | None
    content: dict[str, object]
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProposalListResponse(BaseModel):
    items: list[ProposalResponse]
    total: int


class ProposalReviewCreate(BaseModel):
    decision: ReviewDecision
    comment: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def require_comment_for_revision(self) -> "ProposalReviewCreate":
        if self.decision != ReviewDecision.APPROVED and not (self.comment or "").strip():
            raise ValueError("comment is required when rejecting or requesting changes")
        return self


class ProposalReviewResponse(BaseModel):
    id: str
    proposal_id: str
    decision: str
    comment: str | None
    created_at: datetime
    updated_at: datetime


class ProposalReviewListResponse(BaseModel):
    items: list[ProposalReviewResponse]
    total: int


class ProposalReviewResult(BaseModel):
    proposal: ProposalResponse
    review: ProposalReviewResponse
