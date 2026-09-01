from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RFPCreateResponse(BaseModel):
    rfp_id: str
    document_id: str
    workflow_run_id: str
    status: str
    current_stage: str
    event_id: str
    event_status: Literal["PENDING", "PUBLISHED", "FAILED"]
    created_at: datetime


class RFPResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    title: str
    reference_number: str | None
    status: str
    current_stage: str
    priority: str
    source_language: str | None
    due_at: datetime | None
    processing_started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_type: str
    status: str
    original_filename: str
    content_type: str
    size_bytes: int
    page_count: int | None
    parsed_text_object_key: str | None
    parsed_ir_object_key: str | None
    created_at: datetime


class WorkflowRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_type: str
    status: str
    current_node: str | None
    correlation_id: str
    attempt: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class RFPDetailResponse(RFPResponse):
    documents: list[DocumentSummary]
    workflow_runs: list[WorkflowRunSummary]


class RFPListResponse(BaseModel):
    items: list[RFPResponse]
    total: int
    offset: int
    limit: int


class RFPStatusResponse(BaseModel):
    rfp_id: str
    status: str
    current_stage: str
    stage_label: str
    progress_percent: int
    stage_started_at: datetime | None
    elapsed_seconds: int
    attempt: int
    is_terminal: bool
    error_message: str | None
    processing_started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class RFPRetryResponse(BaseModel):
    rfp_id: str
    workflow_run_id: str
    retried_stage: str
    attempt: int
    status: str
    current_stage: str
    event_id: str
    event_status: Literal["PENDING", "PUBLISHED", "FAILED"]
    queued_at: datetime
