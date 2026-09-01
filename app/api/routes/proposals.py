from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.api.dependencies import get_proposal_review_service, get_proposal_service
from app.core.exceptions import (
    ObjectStorageError,
    ProposalNotFoundError,
    ProposalReviewConflictError,
)
from app.models import ProposalReview
from app.schemas.proposal import (
    ProposalResponse,
    ProposalReviewCreate,
    ProposalReviewListResponse,
    ProposalReviewResponse,
    ProposalReviewResult,
)
from app.services.proposal import ProposalService
from app.services.proposal_review import ProposalReviewService

router = APIRouter(prefix="/proposals", tags=["proposals"])


def _review_response(review: ProposalReview) -> ProposalReviewResponse:
    return ProposalReviewResponse(
        id=review.id,
        proposal_id=review.proposal_id,
        decision=review.decision,
        comment=review.comment,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: UUID,
    service: Annotated[ProposalService, Depends(get_proposal_service)],
) -> ProposalResponse:
    try:
        proposal = await service.get(str(proposal_id))
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProposalResponse.model_validate(proposal)


@router.get("/{proposal_id}/markdown", response_class=PlainTextResponse)
async def get_proposal_markdown(
    proposal_id: UUID,
    service: Annotated[ProposalService, Depends(get_proposal_service)],
) -> PlainTextResponse:
    try:
        markdown = await service.get_markdown(str(proposal_id))
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return PlainTextResponse(markdown, media_type="text/markdown")


@router.post("/{proposal_id}/reviews", response_model=ProposalReviewResult)
async def review_proposal(
    proposal_id: UUID,
    data: ProposalReviewCreate,
    service: Annotated[ProposalReviewService, Depends(get_proposal_review_service)],
) -> ProposalReviewResult:
    try:
        outcome = await service.review(str(proposal_id), data)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProposalReviewConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return ProposalReviewResult(
        proposal=ProposalResponse.model_validate(outcome.proposal),
        review=_review_response(outcome.review),
    )


@router.get("/{proposal_id}/reviews", response_model=ProposalReviewListResponse)
async def list_proposal_reviews(
    proposal_id: UUID,
    service: Annotated[ProposalReviewService, Depends(get_proposal_review_service)],
) -> ProposalReviewListResponse:
    try:
        reviews = await service.list_reviews(str(proposal_id))
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProposalReviewListResponse(
        items=[_review_response(item) for item in reviews],
        total=len(reviews),
    )
