from collections.abc import Sequence
from typing import Protocol

from app.core.config import Settings
from app.core.exceptions import RequirementExtractionError
from app.llm.structured_chat import StructuredChatClient, llm_error_summary
from app.schemas.requirement import ExtractedRequirement, RequirementExtractionBatch

ANALYST_INSTRUCTIONS = """
You are the RFP Analyst Agent for an enterprise proposal system.
Extract every independently actionable customer requirement from the supplied RFP text.

Rules:
- Decompose compound statements into atomic requirements.
- Preserve the customer's meaning in requirement_text.
- Write normalized_text as a concise, vendor-neutral requirement.
- Use a short lowercase category such as security, compliance, integration, deployment,
  functionality, performance, support, commercial, data, or migration.
- mandatory is true only when the source uses mandatory language such as must, shall,
  required, mandatory, or an equivalent unambiguous expression.
- Page markers look like "--- Page 13 ---". Record the source page when available.
  Page numbers must be positive integers; use null (not 0 or an empty string) when
  no page marker is available. source_page_end must not precede source_page_start.
- source_quote must be a short verbatim excerpt supporting the requirement.
- confidence measures extraction certainty, not the vendor's ability to satisfy it.
  It must be a number between 0 and 1 inclusive, never a percentage or percentage string.
- Each requirement must include category, requirement_text, normalized_text, mandatory,
  and confidence. Text fields must not be empty; mandatory must be a JSON boolean.
- The top-level object must contain only requirements. Do not add undefined fields.
- Do not invent requirements and do not evaluate vendor capability.
- Return an empty requirements list when the chunk contains no requirements.
""".strip()


class RequirementExtractor(Protocol):
    async def extract(
        self,
        document_text: str,
        *,
        rfp_id: str,
        title: str,
    ) -> list[ExtractedRequirement]: ...


class OpenAIRequirementExtractor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = StructuredChatClient(settings)

    async def extract(
        self,
        document_text: str,
        *,
        rfp_id: str,
        title: str,
    ) -> list[ExtractedRequirement]:
        chunks = self._split_text(document_text)
        extracted: list[ExtractedRequirement] = []
        for index, chunk in enumerate(chunks, start=1):
            try:
                response = await self.client.complete(
                    instructions=ANALYST_INSTRUCTIONS,
                    user_input=(
                        f"RFP ID: {rfp_id}\n"
                        f"RFP title: {title}\n"
                        f"Document chunk: {index}/{len(chunks)}\n\n"
                        f"{chunk}"
                    ),
                    output_model=RequirementExtractionBatch,
                    max_tokens=self.settings.requirement_max_output_tokens,
                    operation="extract_requirements",
                    correlation_id=rfp_id,
                )
            except Exception as exc:
                raise RequirementExtractionError(
                    f"LLM requirement extraction failed for chunk {index}: {llm_error_summary(exc)}"
                ) from exc
            extracted.extend(response.requirements)
        return extracted

    def _split_text(self, text: str) -> Sequence[str]:
        chunk_size = self.settings.requirement_chunk_size_chars
        if chunk_size < 1:
            raise RequirementExtractionError("REQUIREMENT_CHUNK_SIZE_CHARS must be positive")

        chunks: list[str] = []
        remaining = text.strip()
        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break
            boundary = remaining.rfind("\n\n", 0, chunk_size)
            if boundary < chunk_size // 2:
                boundary = chunk_size
            chunks.append(remaining[:boundary].strip())
            remaining = remaining[boundary:].strip()

        if not chunks:
            raise RequirementExtractionError("parsed document text is empty")
        if len(chunks) > self.settings.requirement_max_chunks:
            raise RequirementExtractionError(
                "parsed document exceeds the configured requirement extraction limit"
            )
        return chunks
