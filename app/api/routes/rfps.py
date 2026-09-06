from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.dependencies import (
    get_capability_service,
    get_proposal_service,
    get_requirement_service,
    get_rfp_service,
)
from app.core.exceptions import (
    CustomerNotFoundError,
    EmptyUploadError,
    ObjectStorageError,
    RFPConflictError,
    RFPNotFoundError,
    RFPRetryConflictError,
    UnsupportedDocumentError,
    UploadTooLargeError,
)
from app.models.enums import Priority, RFPStatus
from app.models.mixins import utc_now
from app.schemas.capability import (
    CapabilityEvidenceResponse,
    CapabilityResultListResponse,
    CapabilityResultResponse,
)
from app.schemas.proposal import ProposalListResponse, ProposalResponse
from app.schemas.requirement import RequirementListResponse, RequirementResponse
from app.schemas.rfp import (
    RFPCreateResponse,
    RFPDetailResponse,
    RFPListResponse,
    RFPResponse,
    RFPRetryResponse,
    RFPStatusResponse,
)
from app.services.capability import CapabilityService
from app.services.proposal import ProposalService
from app.services.requirement import RequirementService
from app.services.rfp import CreateRFPCommand, RFPService

router = APIRouter(prefix="/rfps", tags=["rfps"])


@router.delete("/{rfp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rfp(
    rfp_id: UUID,
    service: Annotated[RFPService, Depends(get_rfp_service)],
) -> Response:
    try:
        await service.delete(str(rfp_id))
    except RFPNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


_STAGE_PROGRESS = {
    "queued": (5, "等待处理"),
    "parse_document": (10, "解析文档"),
    "document_parsed": (25, "文档解析完成"),
    "extract_requirements": (30, "抽取需求"),
    "requirements_extracted": (50, "需求抽取完成"),
    "evaluate_capabilities": (55, "能力判断"),
    "capabilities_evaluated": (75, "能力判断完成"),
    "generate_proposal": (80, "生成方案"),
    "proposal_revision": (80, "修改方案"),
    "human_review": (95, "等待人工审核"),
    "approved": (100, "已通过审核"),
}


@router.get("", response_model=RFPListResponse)
async def list_rfps(
    service: Annotated[RFPService, Depends(get_rfp_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    customer_id: UUID | None = None,
    rfp_status: Annotated[RFPStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=255)] = None,
) -> RFPListResponse:
    page = await service.list(
        offset=offset,
        limit=limit,
        customer_id=str(customer_id) if customer_id else None,
        status=rfp_status.value if rfp_status else None,
        search=search,
    )
    return RFPListResponse(
        items=[RFPResponse.model_validate(rfp) for rfp in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/{rfp_id}", response_model=RFPDetailResponse)
async def get_rfp(
    rfp_id: UUID,
    service: Annotated[RFPService, Depends(get_rfp_service)],
) -> RFPDetailResponse:
    try:
        rfp = await service.get(str(rfp_id))
    except RFPNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RFPDetailResponse.model_validate(rfp)


@router.get("/{rfp_id}/status", response_model=RFPStatusResponse)
async def get_rfp_status(
    rfp_id: UUID,
    service: Annotated[RFPService, Depends(get_rfp_service)],
) -> RFPStatusResponse:
    try:
        rfp = await service.get(str(rfp_id))
    except RFPNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    progress_percent, stage_label = _STAGE_PROGRESS.get(
        rfp.current_stage,
        (0, rfp.current_stage.replace("_", " ")),
    )
    if rfp.status in {RFPStatus.APPROVED.value, RFPStatus.COMPLETED.value}:
        progress_percent = 100
    stage_started_at = rfp.stage_started_at
    elapsed_end = (
        utc_now()
        if rfp.status in {RFPStatus.QUEUED.value, RFPStatus.PROCESSING.value}
        else rfp.updated_at
    )
    elapsed_seconds = (
        max(0, int((elapsed_end - stage_started_at).total_seconds())) if stage_started_at else 0
    )
    latest_workflow = max(rfp.workflow_runs, key=lambda item: item.created_at, default=None)
    return RFPStatusResponse(
        rfp_id=rfp.id,
        status=rfp.status,
        current_stage=rfp.current_stage,
        stage_label=stage_label,
        progress_percent=progress_percent,
        stage_started_at=stage_started_at,
        elapsed_seconds=elapsed_seconds,
        attempt=latest_workflow.attempt if latest_workflow else 0,
        is_terminal=rfp.status
        in {
            RFPStatus.APPROVED.value,
            RFPStatus.COMPLETED.value,
            RFPStatus.FAILED.value,
            RFPStatus.ARCHIVED.value,
        },
        error_message=rfp.error_message,
        processing_started_at=rfp.processing_started_at,
        completed_at=rfp.completed_at,
        updated_at=rfp.updated_at,
    )


@router.post(
    "/{rfp_id}/retry",
    response_model=RFPRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_rfp(
    rfp_id: UUID,
    service: Annotated[RFPService, Depends(get_rfp_service)],
) -> RFPRetryResponse:
    try:
        result = await service.retry(str(rfp_id))
    except RFPNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RFPRetryConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RFPRetryResponse(
        rfp_id=result.rfp.id,
        workflow_run_id=result.workflow_run.id,
        retried_stage=result.retried_stage,
        attempt=result.workflow_run.attempt,
        status=result.rfp.status,
        current_stage=result.rfp.current_stage,
        event_id=result.event.id,
        event_status=result.event_status,
        queued_at=result.queued_at,
    )


@router.get("/{rfp_id}/requirements", response_model=RequirementListResponse)
async def list_rfp_requirements(
    rfp_id: UUID,
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> RequirementListResponse:
    try:
        requirements = await service.list_for_rfp(str(rfp_id))
    except RFPNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RequirementListResponse(
        items=[RequirementResponse.model_validate(item) for item in requirements],
        total=len(requirements),
    )


@router.get("/{rfp_id}/capabilities", response_model=CapabilityResultListResponse)
async def list_rfp_capabilities(
    rfp_id: UUID,
    service: Annotated[CapabilityService, Depends(get_capability_service)],
) -> CapabilityResultListResponse:
    try:
        results = await service.list_for_rfp(str(rfp_id))
    except RFPNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CapabilityResultListResponse(
        items=[
            CapabilityResultResponse(
                id=result.id,
                requirement_id=result.requirement_id,
                requirement_key=result.requirement.requirement_key,
                requirement_text=result.requirement.requirement_text,
                status=result.status,
                confidence=float(result.confidence) if result.confidence is not None else None,
                reason=result.reason,
                customization_notes=result.customization_notes,
                model_name=result.model_name,
                prompt_version=result.prompt_version,
                citation_audit=result.citation_audit,
                evidence=[
                    CapabilityEvidenceResponse.model_validate(item)
                    for item in sorted(
                        result.evidence_items,
                        key=lambda evidence: evidence.rank_position,
                    )
                ],
                created_at=result.created_at,
                updated_at=result.updated_at,
            )
            for result in results
        ],
        total=len(results),
    )


@router.get("/{rfp_id}/proposals", response_model=ProposalListResponse)
async def list_rfp_proposals(
    rfp_id: UUID,
    service: Annotated[ProposalService, Depends(get_proposal_service)],
) -> ProposalListResponse:
    try:
        proposals = await service.list_for_rfp(str(rfp_id))
    except RFPNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProposalListResponse(
        items=[ProposalResponse.model_validate(item) for item in proposals],
        total=len(proposals),
    )


@router.post("", response_model=RFPCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_rfp(
    file: Annotated[UploadFile, File(description="RFP document in PDF or DOCX format")],
    customer_id: Annotated[UUID, Form()],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    service: Annotated[RFPService, Depends(get_rfp_service)],
    reference_number: Annotated[str | None, Form(max_length=100)] = None,
    priority: Annotated[Priority, Form()] = Priority.NORMAL,
    source_language: Annotated[str | None, Form(max_length=16)] = None,
    due_at: Annotated[datetime | None, Form()] = None,
) -> RFPCreateResponse:
    command = CreateRFPCommand(
        customer_id=str(customer_id),
        title=title,
        reference_number=reference_number,
        priority=priority.value,
        source_language=source_language,
        due_at=due_at,
    )
    try:
        result = await service.create(command, file)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except EmptyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RFPConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    finally:
        await file.close()

    return RFPCreateResponse(
        rfp_id=result.rfp.id,
        document_id=result.document.id,
        workflow_run_id=result.workflow_run.id,
        status=result.rfp.status,
        current_stage=result.rfp.current_stage,
        event_id=result.event.id,
        event_status=result.event_status,
        created_at=result.rfp.created_at,
    )
