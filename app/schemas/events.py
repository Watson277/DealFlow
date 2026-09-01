from typing import Literal

from pydantic import BaseModel


class RFPUploadedEvent(BaseModel):
    event_id: str
    event_type: Literal["rfp.uploaded"]
    occurred_at: str
    rfp_id: str
    document_id: str
    workflow_run_id: str
    correlation_id: str


class RFPCompletedEvent(BaseModel):
    event_id: str
    event_type: Literal["rfp.completed"]
    occurred_at: str
    rfp_id: str
    document_id: str
    workflow_run_id: str
    parsed_text_object_key: str


class RequirementsExtractedEvent(BaseModel):
    event_id: str
    event_type: Literal["rfp.requirements.extracted"]
    occurred_at: str
    rfp_id: str
    document_id: str
    workflow_run_id: str
    requirement_count: int


class CapabilitiesEvaluatedEvent(BaseModel):
    event_id: str
    event_type: Literal["rfp.capabilities.evaluated"]
    occurred_at: str
    rfp_id: str
    workflow_run_id: str
    capability_count: int


class ProposalGeneratedEvent(BaseModel):
    event_id: str
    event_type: Literal["proposal.generated"]
    occurred_at: str
    rfp_id: str
    workflow_run_id: str
    proposal_id: str
    version: int


class ProposalApprovedEvent(BaseModel):
    event_id: str
    event_type: Literal["proposal.approved"]
    occurred_at: str
    rfp_id: str
    workflow_run_id: str
    proposal_id: str
    version: int
