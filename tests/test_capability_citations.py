from datetime import UTC

import pytest

from app.agents.capability_citations import validate_capability_citations
from app.core.exceptions import CapabilityEvaluationError
from app.models.enums import CapabilityStatus
from app.rag.vector_store import RetrievedEvidence
from app.schemas.capability import CapabilityJudgment


def _evidence(point_id: str) -> RetrievedEvidence:
    return RetrievedEvidence(
        point_id=point_id,
        document_id="document-1",
        title="Security Guide",
        version="1.0",
        category="security",
        page_number=3,
        text="SAML 2.0 is supported.",
        score=0.95,
    )


def _judgment(
    status: CapabilityStatus,
    selected_ids: list[str],
) -> CapabilityJudgment:
    return CapabilityJudgment(
        status=status,
        confidence=0.9,
        reason="Evidence-backed conclusion.",
        customization_notes=None,
        selected_evidence_point_ids=selected_ids,
    )


def test_valid_citations_produce_ordered_audit() -> None:
    audit = validate_capability_citations(
        _judgment(CapabilityStatus.SUPPORTED, ["point-2", "point-1"]),
        [_evidence("point-1"), _evidence("point-2")],
    )

    assert audit.available_point_ids == ("point-1", "point-2")
    assert audit.selected_point_ids == ("point-2", "point-1")
    assert audit.selection_order() == {"point-2": 1, "point-1": 2}
    assert audit.validated_at.tzinfo is UTC
    assert audit.as_payload()["validation_status"] == "VALIDATED"


@pytest.mark.parametrize(
    "status",
    [status for status in CapabilityStatus if status is not CapabilityStatus.NEED_REVIEW],
)
def test_decisive_status_requires_at_least_one_citation(status: CapabilityStatus) -> None:
    with pytest.raises(CapabilityEvaluationError, match="requires at least one citation"):
        validate_capability_citations(_judgment(status, []), [_evidence("point-1")])


def test_unknown_citation_is_rejected_instead_of_silently_removed() -> None:
    with pytest.raises(CapabilityEvaluationError, match="outside the supplied evidence set"):
        validate_capability_citations(
            _judgment(CapabilityStatus.SUPPORTED, ["invented-point"]),
            [_evidence("point-1")],
        )


def test_duplicate_citation_is_rejected() -> None:
    with pytest.raises(CapabilityEvaluationError, match="duplicate citations"):
        validate_capability_citations(
            _judgment(CapabilityStatus.SUPPORTED, ["point-1", "point-1"]),
            [_evidence("point-1")],
        )


def test_need_review_can_be_saved_without_citations() -> None:
    audit = validate_capability_citations(
        _judgment(CapabilityStatus.NEED_REVIEW, []),
        [],
    )

    assert audit.available_point_ids == ()
    assert audit.selected_point_ids == ()
