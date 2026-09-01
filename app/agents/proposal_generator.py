from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.core.exceptions import ProposalGenerationError
from app.schemas.proposal import ProposalDraft
from app.services.structured_chat import StructuredChatClient, llm_error_summary

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
            response = await self.client.complete(
                instructions=PROPOSAL_INSTRUCTIONS,
                user_input=context.model_dump_json(),
                output_model=ProposalDraft,
                max_tokens=self.settings.proposal_max_output_tokens,
                operation="generate_proposal",
                correlation_id=str(context.rfp.get("id") or "") or None,
            )
        except Exception as exc:
            raise ProposalGenerationError(llm_error_summary(exc)) from exc
        return response
