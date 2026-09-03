from typing import Any

import pytest

from app.core.config import Settings
from app.rag.reranker import CrossEncoderEvidenceReranker
from app.rag.vector_store import RetrievedEvidence


class FakeTokenizer:
    def encode(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        truncation: bool,
        max_length: int,
    ) -> list[str]:
        assert add_special_tokens is False
        assert truncation is True
        return text.split()[:max_length]

    def decode(self, tokens: list[str], *, skip_special_tokens: bool) -> str:
        assert skip_special_tokens is True
        return " ".join(tokens)


class FakeModel:
    def __init__(self, scores: list[float], *, oom_above: int | None = None) -> None:
        self.tokenizer = FakeTokenizer()
        self.scores = scores
        self.oom_above = oom_above
        self.batch_sizes: list[int] = []
        self.pairs: list[tuple[str, str]] = []

    def predict(
        self,
        pairs: list[tuple[str, str]],
        *,
        batch_size: int,
        **kwargs: Any,
    ) -> list[float]:
        self.batch_sizes.append(batch_size)
        self.pairs = pairs
        if self.oom_above is not None and batch_size > self.oom_above:
            raise RuntimeError("CUDA out of memory")
        return self.scores


def _evidence(index: int, *, child_words: int = 8) -> RetrievedEvidence:
    return RetrievedEvidence(
        point_id=f"child-{index}",
        document_id=f"document-{index}",
        title=f"Guide {index}",
        version="1.0",
        category="security",
        page_number=index,
        text=f"Complete parent text {index}",
        matched_child_text=" ".join(f"word-{word}" for word in range(child_words)),
        score=1.0 / (index + 1),
        parent_id=f"parent-{index}",
        section_path=("Security", "Identity"),
        retrieval_mode="hybrid",
    )


@pytest.mark.asyncio
async def test_cross_encoder_reranks_and_limits_knowledge_to_512_tokens() -> None:
    settings = Settings(
        _env_file=None,
        capability_reranker_enabled=True,
        capability_reranker_device="cpu",
        capability_reranker_batch_size=4,
        capability_reranker_query_max_tokens=16,
        capability_reranker_knowledge_max_tokens=512,
    )
    model = FakeModel([0.2, 0.9, 0.5])
    reranker = CrossEncoderEvidenceReranker(settings)
    reranker._model = model  # noqa: SLF001

    result = await reranker.rerank(
        " ".join(f"query-{index}" for index in range(20)),
        [_evidence(0, child_words=600), _evidence(1), _evidence(2)],
        limit=2,
    )

    assert [item.point_id for item in result] == ["child-1", "child-2"]
    assert [item.rerank_score for item in result] == [0.9, 0.5]
    assert all(len(query.split()) == 16 for query, _ in model.pairs)
    assert all(len(knowledge.split()) <= 512 for _, knowledge in model.pairs)
    assert result[0].text == "Complete parent text 1"


@pytest.mark.asyncio
async def test_cross_encoder_retries_cuda_oom_with_smaller_batch() -> None:
    settings = Settings(
        _env_file=None,
        capability_reranker_enabled=True,
        capability_reranker_device="cpu",
        capability_reranker_batch_size=4,
    )
    model = FakeModel([0.4, 0.3, 0.2, 0.1], oom_above=2)
    reranker = CrossEncoderEvidenceReranker(settings)
    reranker._model = model  # noqa: SLF001

    result = await reranker.rerank("query", [_evidence(i) for i in range(4)], limit=4)

    assert model.batch_sizes == [4, 2]
    assert [item.rerank_score for item in result] == [0.4, 0.3, 0.2, 0.1]


@pytest.mark.asyncio
async def test_cross_encoder_failure_falls_back_to_rrf_order() -> None:
    settings = Settings(
        _env_file=None,
        capability_reranker_enabled=True,
        capability_reranker_device="cpu",
    )
    model = FakeModel([], oom_above=0)
    reranker = CrossEncoderEvidenceReranker(settings)
    reranker._model = model  # noqa: SLF001
    evidence = [_evidence(0), _evidence(1)]

    result = await reranker.rerank("query", evidence, limit=1)

    assert result == evidence[:1]
    assert result[0].rerank_score is None
