import json
from collections import Counter
from typing import Protocol

import structlog
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.core.exceptions import ProposalGenerationError
from app.llm.structured_chat import (
    LLMOutputTruncatedError,
    StructuredChatClient,
    llm_error_summary,
)
from app.schemas.proposal import (
    ProposalBatch,
    ProposalDraft,
    ProposalRequirementResponse,
    ProposalSections,
)

logger = structlog.get_logger(__name__)

PROPOSAL_INSTRUCTIONS = """
You are the Proposal Agent for an enterprise sales engineering team.
Create a professional, evidence-grounded response to the supplied RFP context.

Rules:
- Use only the supplied customer, requirement, capability, and evidence data.
- Include every requirement exactly once in requirement_responses.
- Preserve each supplied requirement_key and capability_status exactly.
- Never claim full support for NEED_REVIEW, UNSUPPORTED, PARTIALLY_SUPPORTED, or
  REQUIRES_CUSTOMIZATION items.
- Clearly disclose gaps, customization, enterprise-tier restrictions, and missing evidence.
- Do not invent pricing, contractual commitments, certifications, SLA values, or delivery dates.
- Commercial unknowns must be explicitly marked for commercial review.
- Keep the tone confident, precise, and suitable for human review before customer delivery.
""".strip()


class ProposalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfp: dict[str, object]
    customer: dict[str, object]
    capabilities: list[dict[str, object]]


class ProposalGenerator(Protocol):
    async def generate(self, context: ProposalContext) -> ProposalDraft: ...


class OpenAIProposalGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = StructuredChatClient(settings)

    async def generate(self, context: ProposalContext) -> ProposalDraft:
        try:
            keys = [str(item["requirement_key"]) for item in context.capabilities]
            if not keys or len(keys) != len(set(keys)):
                raise ProposalGenerationError("proposal requires unique, nonempty requirements")
            responses: list[ProposalRequirementResponse] = []
            size = self.settings.proposal_batch_size
            for start in range(0, len(keys), size):
                responses.extend(
                    await self._generate_batch(context, context.capabilities[start : start + size])
                )
                logger.info(
                    "proposal_batch_completed",
                    rfp_id=context.rfp.get("id"),
                    completed_requirements=len(responses),
                    total_requirements=len(keys),
                )
            # Evidence summaries and risks are bounded by ProposalBatchItem. Keep every
            # requirement's response, but do not resend raw retrieval snippets.
            overview = {
                "rfp": context.rfp,
                "customer": context.customer,
                "responses": [item.model_dump(mode="json") for item in responses],
            }
            sections = await self.client.complete(
                instructions=(
                    PROPOSAL_INSTRUCTIONS.replace(
                        "- Include every requirement exactly once in requirement_responses.", ""
                    )
                    + "\nGenerate only the overall proposal sections. Do not output a response "
                    "matrix. Keep each section concise (at most 1200 characters). Preserve "
                    "material risks, conditions and numeric commitments from the supplied "
                    "responses. Treat conflicting commitments as unresolved, not as supported."
                ),
                user_input=json.dumps(overview, ensure_ascii=False),
                output_model=ProposalSections,
                max_tokens=self.settings.proposal_max_output_tokens,
                operation="generate_proposal_sections",
                correlation_id=str(context.rfp.get("id") or "") or None,
            )
            return ProposalDraft(
                **sections.model_dump(),
                requirement_responses=responses,
            )
        except ProposalGenerationError:
            raise
        except Exception as exc:
            raise ProposalGenerationError(llm_error_summary(exc)) from exc

    async def _generate_batch(
        self,
        context: ProposalContext,
        capabilities: list[dict[str, object]],
        correction: str = "",
    ) -> list[ProposalRequirementResponse]:
        expected = {str(item["requirement_key"]): item for item in capabilities}
        try:
            batch = await self.client.complete(
                instructions=(
                    PROPOSAL_INSTRUCTIONS
                    + "\nReturn only requirement_responses for this batch. Do not repeat "
                    "requirement text or capability_status in the output; the application "
                    "will restore them. Keep responses concise. Retain numeric constraints, "
                    "SLA, deployment conditions and evidence limitations. Respect field lengths."
                    "\nThe exact required keys for this batch are: "
                    + json.dumps(list(expected), ensure_ascii=False)
                    + ". Copy these keys literally, each exactly once. Do not renumber, "
                    "merge similar requirements, or add keys from evidence documents."
                    + correction
                ),
                user_input=context.model_copy(
                    update={"capabilities": capabilities}
                ).model_dump_json(),
                output_model=ProposalBatch,
                max_tokens=self.settings.proposal_max_output_tokens,
                operation="generate_proposal_batch",
                correlation_id=str(context.rfp.get("id") or "") or None,
            )
        except LLMOutputTruncatedError:
            if len(capabilities) == 1:
                raise
            return await self._split_batch(context, capabilities, reason="truncated")
        actual = [item.requirement_key for item in batch.requirement_responses]
        counts = Counter(actual)
        missing = sorted(set(expected) - set(actual))
        unknown = sorted(set(actual) - set(expected))
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if missing or unknown or duplicates:
            logger.warning(
                "proposal_batch_coverage_failed",
                rfp_id=context.rfp.get("id"),
                requirement_count=len(capabilities),
                missing_keys=missing,
                unknown_keys=unknown,
                duplicate_keys=duplicates,
                correction_attempt=bool(correction),
            )
            if not correction:
                return await self._generate_batch(
                    context,
                    capabilities,
                    correction=(
                        "\nThe previous attempt had invalid requirement coverage: "
                        + json.dumps(
                            {"missing": missing, "unknown": unknown, "duplicates": duplicates},
                            ensure_ascii=False,
                        )
                        + ". Regenerate the complete batch from the supplied source data, "
                        "not just the missing items. Match each response to its source key."
                    ),
                )
            if len(capabilities) > 1:
                return await self._split_batch(context, capabilities, reason="coverage")
            raise ProposalGenerationError(
                "proposal batch must contain every supplied requirement exactly once; "
                f"coverage repair exhausted for {next(iter(expected))} "
                f"(missing={len(missing)}, unknown={len(unknown)}, duplicates={len(duplicates)})"
            )
        by_key = {item.requirement_key: item for item in batch.requirement_responses}
        return [
            ProposalRequirementResponse.model_validate(
                {
                    **by_key[key].model_dump(),
                    "requirement": source["requirement"],
                    "capability_status": source["capability_status"],
                }
            )
            for key, source in expected.items()
        ]

    async def _split_batch(
        self,
        context: ProposalContext,
        capabilities: list[dict[str, object]],
        *,
        reason: str,
    ) -> list[ProposalRequirementResponse]:
        logger.warning(
            "proposal_batch_split",
            rfp_id=context.rfp.get("id"),
            requirement_count=len(capabilities),
            reason=reason,
        )
        middle = len(capabilities) // 2
        left = await self._generate_batch(context, capabilities[:middle])
        right = await self._generate_batch(context, capabilities[middle:])
        return left + right
