from collections.abc import Sequence
from typing import Protocol

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.exceptions import EmbeddingError, LLMConfigurationError


class EmbeddingService(Protocol):
    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AsyncOpenAI | None = None

    @property
    def dimensions(self) -> int:
        return self.settings.embedding_dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        vectors: list[list[float]] = []
        batch_size = self.settings.embedding_batch_size
        if batch_size < 1:
            raise LLMConfigurationError("EMBEDDING_BATCH_SIZE must be positive")
        for start in range(0, len(texts), batch_size):
            try:
                response = await client.embeddings.create(
                    model=self.settings.embedding_model,
                    input=list(texts[start : start + batch_size]),
                    dimensions=self.settings.embedding_dimensions,
                )
            except Exception as exc:
                raise EmbeddingError("LLM provider embedding request failed") from exc
            vectors.extend(item.embedding for item in response.data)
        return vectors

    def _get_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client
        if self.settings.llm_api_key is None:
            raise LLMConfigurationError("LLM_API_KEY (or ZAI_API_KEY) is required for embeddings")
        api_key = self.settings.llm_api_key.get_secret_value().strip()
        if not api_key:
            raise LLMConfigurationError("LLM_API_KEY (or ZAI_API_KEY) is required for embeddings")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout_seconds,
        )
        return self._client
