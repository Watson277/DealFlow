import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError, RequirementExtractionError
from app.llm.structured_chat import StructuredChatClient, llm_error_summary
from app.rag.tokenization import TokenCounter
from app.schemas.requirement import ExtractedRequirement, RequirementExtractionBatch

ANALYST_INSTRUCTIONS = """
You are the RFP Analyst Agent for an enterprise proposal system.
Extract customer requirements at the granularity used by the RFP for supplier responses.

Rules:
- When the RFP has numbered requirement items (for example, B-001), return exactly
  one record per complete numbered item. Keep all its limits, conditions, exceptions,
  service levels, and commercial terms together, even if they could be checked separately.
- Do not split an item because it contains "and", multiple numbers, protocols, deliverables,
  or deadlines. For example, an item requiring both 2500 accounts and 400 concurrent users
  is one requirement containing both thresholds.
- Start requirement_text with the source item identifier exactly as printed, followed by
  a faithful description of the whole item. This identifies repeated items in overlapping
  chunks. Write normalized_text as a vendor-neutral, self-contained description of the
  whole item without the identifier; preserve every acceptance condition and qualifier.
- If a numbered item is cut off at a chunk boundary, do not extract the fragment. Extract
  the item only from a chunk containing its complete text. Do not extract the same item
  twice within a chunk.
- If the RFP has no numbered items, group related conditions that the supplier can answer
  as one capability or deliverable. Split only genuinely unrelated requests.
- Extract supplier-facing product, service, delivery, or commercial requirements. Do not
  turn background, section headings, headers/footers, evaluation guidance, or instructions
  about how to write the proposal into separate requirements.
- Use a short lowercase category such as security, compliance, integration, deployment,
  functionality, performance, support, commercial, data, or migration.
- An explicitly optional item has mandatory=false even if it contains a conditional
  obligation. Otherwise mandatory is true only for must, shall, required, mandatory,
  or an equivalent unambiguous expression, including a visible document-wide rule.
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

    async def aclose(self) -> None:
        await self.client.client.close()

    async def extract(
        self,
        document_text: str,
        *,
        rfp_id: str,
        title: str,
    ) -> list[ExtractedRequirement]:
        extracted: list[ExtractedRequirement] = []
        async for batch in self.extract_chunks(document_text, rfp_id=rfp_id, title=title):
            extracted.extend(batch)
        return extracted

    async def extract_chunks(
        self,
        document_text: str,
        *,
        rfp_id: str,
        title: str,
    ) -> AsyncIterator[list[ExtractedRequirement]]:
        chunks = self._split_text(document_text)
        semaphore = asyncio.Semaphore(self.settings.requirement_chunk_concurrency)

        async def extract_one(index: int, chunk: str) -> list[ExtractedRequirement]:
            async with semaphore:
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
                        f"LLM requirement extraction failed for chunk {index}: "
                        f"{llm_error_summary(exc)}"
                    ) from exc
                return response.requirements

        tasks = [
            asyncio.create_task(extract_one(index, chunk))
            for index, chunk in enumerate(chunks, start=1)
        ]
        try:
            for task in tasks:
                yield await task
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _split_text(self, text: str) -> Sequence[str]:
        try:
            counter = TokenCounter(self.settings.requirement_tokenizer_encoding)
            chunks = counter.split(
                text,
                budget=self.settings.requirement_chunk_size_tokens,
                overlap=self.settings.requirement_chunk_overlap_tokens,
            )
        except KnowledgeIndexError as exc:
            raise RequirementExtractionError(
                "invalid requirement token chunk configuration"
            ) from exc

        if not chunks:
            raise RequirementExtractionError("parsed document text is empty")
        if len(chunks) > self.settings.requirement_max_chunks:
            raise RequirementExtractionError(
                "parsed document exceeds the configured requirement extraction limit"
            )
        return chunks
