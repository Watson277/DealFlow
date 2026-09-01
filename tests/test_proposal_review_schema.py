import pytest
from pydantic import ValidationError

from app.models.enums import ReviewDecision
from app.schemas.proposal import ProposalReviewCreate


def test_revision_decision_requires_comment() -> None:
    with pytest.raises(ValidationError, match="comment is required"):
        ProposalReviewCreate(
            decision=ReviewDecision.CHANGES_REQUESTED,
        )


def test_approval_does_not_require_comment() -> None:
    review = ProposalReviewCreate(
        decision=ReviewDecision.APPROVED,
    )

    assert review.comment is None
