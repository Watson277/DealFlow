import json
from dataclasses import asdict, dataclass
from typing import Protocol

from app.core.config import Settings
from app.core.exceptions import CapabilityEvaluationError
from app.schemas.capability import CapabilityJudgment
from app.services.structured_chat import StructuredChatClient, llm_error_summary
from app.services.vector_store import RetrievedEvidence

CAPABILITY_INSTRUCTIONS = """
You are the Capability Agent for an enterprise proposal system.
Judge whether the vendor can satisfy one customer requirement using only the supplied
enterprise knowledge evidence.

Allowed statuses:
- SUPPORTED: evidence directly confirms full support.
- PARTIALLY_SUPPORTED: evidence confirms only part of the requirement.
- UNSUPPORTED: evidence explicitly contradicts or excludes the requirement.
- ENTERPRISE_ONLY: evidence says the capability is limited to an enterprise tier.
- REQUIRES_CUSTOMIZATION: evidence says custom engineering or configuration is required.
- NEED_REVIEW: evidence is absent, ambiguous, stale, or insufficient.

Rules:
- Never use outside knowledge and never invent a capability.
- Cite evidence through selected_evidence_point_ids, using only supplied point IDs.
- Explain the evidence-to-conclusion relationship in reason.
- Low or conflicting evidence must produce NEED_REVIEW.
- confidence is confidence in this judgment, not retrieval similarity.
""".strip()


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    id: str
    key: str
    text: str
    category: str
    mandatory: bool
    rfp_id: str | None = None


class CapabilityJudge(Protocol):
    async def judge(
        self,
        requirement: CapabilityRequirement,
        evidence: list[RetrievedEvidence],
    ) -> CapabilityJudgment: ...


class OpenAICapabilityJudge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = StructuredChatClient(settings)

    async def judge(
        self,
        requirement: CapabilityRequirement,
        evidence: list[RetrievedEvidence],
    ) -> CapabilityJudgment:
        evidence_payload = [
            {
                "point_id": item.point_id,
                "document_id": item.document_id,
                "title": item.title,
                "version": item.version,
                "page": item.page_number,
                "category": item.category,
                "retrieval_score": item.score,
                "text": item.text,
            }
            for item in evidence
        ]
        try:
            response = await self.client.complete(
                instructions=CAPABILITY_INSTRUCTIONS,
                user_input=(
                    "Requirement:\n"
                    f"{json.dumps(asdict(requirement), ensure_ascii=False)}\n\n"
                    "Retrieved enterprise evidence:\n"
                    f"{json.dumps(evidence_payload, ensure_ascii=False)}"
                ),
                output_model=CapabilityJudgment,
                max_tokens=self.settings.capability_max_output_tokens,
                operation="evaluate_capability",
                correlation_id=requirement.rfp_id or requirement.id,
            )
        except Exception as exc:
            raise CapabilityEvaluationError(llm_error_summary(exc)) from exc

        available_ids = {item.point_id for item in evidence}
        response.selected_evidence_point_ids = [
            point_id
            for point_id in response.selected_evidence_point_ids
            if point_id in available_ids
        ]
        return response
