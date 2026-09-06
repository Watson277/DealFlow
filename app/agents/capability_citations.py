from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.exceptions import CapabilityEvaluationError
from app.models.enums import CapabilityStatus
from app.rag.vector_store import RetrievedEvidence
from app.schemas.capability import CapabilityJudgment


@dataclass(frozen=True, slots=True)
class CapabilityCitationAudit:
    available_point_ids: tuple[str, ...]
    selected_point_ids: tuple[str, ...]
    validated_at: datetime

    def as_payload(self) -> dict[str, object]:
        return {
            "validation_status": "VALIDATED",
            "policy": "NON_REVIEW_STATUSES_REQUIRE_CITATION",
            "available_point_ids": list(self.available_point_ids),
            "selected_point_ids": list(self.selected_point_ids),
            "evidence_count": len(self.available_point_ids),
            "selected_count": len(self.selected_point_ids),
            "validated_at": self.validated_at.isoformat(),
        }

    def selection_order(self) -> dict[str, int]:
        return {
            point_id: order
            for order, point_id in enumerate(self.selected_point_ids, start=1)
        }


def validate_capability_citations(
    judgment: CapabilityJudgment,
    evidence: list[RetrievedEvidence],
) -> CapabilityCitationAudit:
    """Validate an LLM judgment against the exact evidence set it received."""

    available_ids = tuple(item.point_id for item in evidence)
    if len(available_ids) != len(set(available_ids)):
        raise CapabilityEvaluationError("capability evidence contains duplicate point IDs")

    selected_ids = tuple(judgment.selected_evidence_point_ids)
    if len(selected_ids) != len(set(selected_ids)):
        raise CapabilityEvaluationError("capability judgment contains duplicate citations")

    unknown_ids = sorted(set(selected_ids).difference(available_ids))
    if unknown_ids:
        raise CapabilityEvaluationError(
            "capability judgment cited evidence outside the supplied evidence set: "
            + ", ".join(unknown_ids)
        )

    if judgment.status is not CapabilityStatus.NEED_REVIEW and not selected_ids:
        raise CapabilityEvaluationError(
            f"{judgment.status.value} capability judgment requires at least one citation"
        )

    return CapabilityCitationAudit(
        available_point_ids=available_ids,
        selected_point_ids=selected_ids,
        validated_at=datetime.now(UTC),
    )
