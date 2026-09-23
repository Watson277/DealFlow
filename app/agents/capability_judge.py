import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Protocol

import structlog

from app.agents.capability_citations import validate_capability_citations
from app.core.config import Settings
from app.core.exceptions import CapabilityEvaluationError
from app.llm.structured_chat import (
    LLMOutputTruncatedError,
    StructuredChatClient,
    llm_error_summary,
)
from app.rag.vector_store import RetrievedEvidence
from app.schemas.capability import CapabilityBatchJudgment, CapabilityJudgment

logger = structlog.get_logger(__name__)

CAPABILITY_INSTRUCTIONS = """
You are the Capability Agent for an enterprise proposal system.
Judge whether the vendor can satisfy each customer requirement using only the enterprise
knowledge evidence supplied with that requirement.

Allowed statuses:
- SUPPORTED: evidence directly confirms full support.
- PARTIALLY_SUPPORTED: evidence confirms only part of the requirement.
- UNSUPPORTED: evidence explicitly contradicts or excludes the requirement.
- ENTERPRISE_ONLY: evidence says the capability is limited to an enterprise tier.
- REQUIRES_CUSTOMIZATION: evidence says custom engineering or configuration is required.
- NEED_REVIEW: evidence is absent, ambiguous, stale, or insufficient.

Rules:
- Never use outside knowledge and never invent a capability.
- Return one judgment for every supplied requirement_key, exactly once.
- Keep evidence isolated: a judgment may cite only point IDs supplied with that requirement.
- Cite evidence through selected_evidence_point_ids, using only supplied point IDs.
- Every status except NEED_REVIEW must cite at least one supplied point ID.
- Do not repeat a point ID in selected_evidence_point_ids.
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
    async def judge_batch(
        self,
        items: list[tuple[CapabilityRequirement, list[RetrievedEvidence]]],
    ) -> dict[str, CapabilityJudgment]: ...


class OpenAICapabilityJudge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = StructuredChatClient(settings)

    async def judge_batch(
        self,
        items: list[tuple[CapabilityRequirement, list[RetrievedEvidence]]],
    ) -> dict[str, CapabilityJudgment]:
        if not items:
            return {}
        keys = [requirement.key for requirement, _ in items]
        if len(keys) != len(set(keys)):
            raise CapabilityEvaluationError(
                "capability batch requires unique requirement keys"
            )
        if len(items) > self.settings.capability_batch_size:
            raise CapabilityEvaluationError(
                "capability batch exceeds configured batch size"
            )
        try:
            return await self._generate_batch(items)
        except CapabilityEvaluationError:
            raise
        except Exception as exc:
            raise CapabilityEvaluationError(llm_error_summary(exc)) from exc

    async def _generate_batch(
        self,
        items: list[tuple[CapabilityRequirement, list[RetrievedEvidence]]],
        correction: str = "",
    ) -> dict[str, CapabilityJudgment]:
        expected = {requirement.key: evidence for requirement, evidence in items}
        payload = [
            {
                "requirement": asdict(requirement),
                "evidence": [self._evidence_payload(item) for item in evidence],
            }
            for requirement, evidence in items
        ]
        try:
            response = await self.client.complete(
                instructions=(
                    CAPABILITY_INSTRUCTIONS
                    + "\nThe exact required requirement_keys for this batch are: "
                    + json.dumps(list(expected), ensure_ascii=False)
                    + ". Copy each key literally and do not merge or renumber requirements."
                    + correction
                ),
                user_input=json.dumps({"items": payload}, ensure_ascii=False),
                output_model=CapabilityBatchJudgment,
                max_tokens=self.settings.capability_max_output_tokens,
                operation="evaluate_capability_batch",
                correlation_id=items[0][0].rfp_id or items[0][0].id,
            )
        except LLMOutputTruncatedError:
            if len(items) == 1:
                raise CapabilityEvaluationError(
                    f"capability batch output was truncated for {items[0][0].key}"
                ) from None
            return await self._split_batch(items, reason="truncated")

        actual = [item.requirement_key for item in response.judgments]
        counts = Counter(actual)
        missing = sorted(set(expected) - set(actual))
        unknown = sorted(set(actual) - set(expected))
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        by_key = {item.requirement_key: item for item in response.judgments}
        citation_errors: dict[str, str] = {}
        judgments: dict[str, CapabilityJudgment] = {}
        if not (missing or unknown or duplicates):
            for key, evidence in expected.items():
                item = by_key[key]
                judgment = CapabilityJudgment.model_validate(
                    item.model_dump(exclude={"requirement_key"})
                )
                try:
                    validate_capability_citations(judgment, evidence)
                except CapabilityEvaluationError as exc:
                    citation_errors[key] = str(exc)
                judgments[key] = judgment

        if not (missing or unknown or duplicates or citation_errors):
            return judgments

        diagnostics = {
            "missing": missing,
            "unknown": unknown,
            "duplicates": duplicates,
            "citation_errors": citation_errors,
        }
        logger.warning(
            "capability_batch_validation_failed",
            rfp_id=items[0][0].rfp_id,
            requirement_count=len(items),
            correction_attempt=bool(correction),
            **diagnostics,
        )
        if not correction:
            return await self._generate_batch(
                items,
                correction=(
                    "\nThe previous response failed batch validation: "
                    + json.dumps(diagnostics, ensure_ascii=False)
                    + ". Regenerate the COMPLETE batch from the supplied items."
                ),
            )
        if len(items) > 1:
            return await self._split_batch(items, reason="validation")
        raise CapabilityEvaluationError(
            f"capability batch repair exhausted for {items[0][0].key}"
        )

    async def _split_batch(
        self,
        items: list[tuple[CapabilityRequirement, list[RetrievedEvidence]]],
        *,
        reason: str,
    ) -> dict[str, CapabilityJudgment]:
        logger.warning(
            "capability_batch_split",
            rfp_id=items[0][0].rfp_id,
            requirement_count=len(items),
            reason=reason,
        )
        middle = len(items) // 2
        left = await self._generate_batch(items[:middle])
        right = await self._generate_batch(items[middle:])
        return {**left, **right}

    @staticmethod
    def _evidence_payload(item: RetrievedEvidence) -> dict[str, object]:
        return {
            "point_id": item.point_id,
            "document_id": item.document_id,
            "title": item.title,
            "version": item.version,
            "page": item.page_number,
            "page_end": item.page_end,
            "section_path": list(item.section_path),
            "block_types": list(item.block_types),
            "source_block_ids": list(item.source_block_ids),
            "parent_id": item.parent_id,
            "category": item.category,
            "retrieval_score": item.score,
            "text": item.text,
        }
