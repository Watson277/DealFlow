import pytest
from pydantic import SecretStr

from app.agents.requirement_extractor import OpenAIRequirementExtractor
from app.core.config import Settings
from app.core.exceptions import LLMConfigurationError, RequirementExtractionError
from app.schemas.requirement import ExtractedRequirement
from app.workflow.stages.extract_requirements import RequirementProcessingService


def test_openai_extractor_requires_api_key() -> None:
    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        OpenAIRequirementExtractor(Settings(llm_api_key=None))


def test_extractor_splits_on_paragraph_boundaries() -> None:
    extractor = OpenAIRequirementExtractor(
        Settings(
            llm_api_key=SecretStr("test-key"),
            requirement_chunk_size_chars=20,
            requirement_max_chunks=3,
        )
    )

    chunks = extractor._split_text("first paragraph\n\nsecond paragraph")

    assert chunks == ["first paragraph", "second paragraph"]


def test_extractor_rejects_documents_over_chunk_limit() -> None:
    extractor = OpenAIRequirementExtractor(
        Settings(
            llm_api_key=SecretStr("test-key"),
            requirement_chunk_size_chars=10,
            requirement_max_chunks=1,
        )
    )

    with pytest.raises(RequirementExtractionError, match="configured"):
        extractor._split_text("first part\n\nsecond part")


def test_requirement_deduplication_keeps_highest_confidence() -> None:
    lower_confidence = ExtractedRequirement(
        category="security",
        requirement_text="SAML is requested.",
        normalized_text="Support  SAML 2.0",
        mandatory=False,
        confidence=0.7,
    )
    higher_confidence = ExtractedRequirement(
        category="security",
        requirement_text="SAML is required.",
        normalized_text="Support SAML 2.0",
        mandatory=True,
        confidence=0.95,
    )

    result = RequirementProcessingService._deduplicate([lower_confidence, higher_confidence])

    assert result == [higher_confidence]
