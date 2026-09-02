import pytest

from app.core.exceptions import KnowledgeIndexError
from app.rag.tokenization import TokenCounter


def test_token_counter_splits_unicode_without_exceeding_budget() -> None:
    counter = TokenCounter("cl100k_base")
    text = "身份认证、审计日志和访问控制能力。" * 80

    parts = counter.split(text, budget=40, overlap=5)

    assert len(parts) > 1
    assert all(counter.count(part) <= 40 for part in parts)
    assert all("�" not in part for part in parts)


def test_token_overlap_repeats_a_bounded_suffix() -> None:
    counter = TokenCounter("cl100k_base")
    text = " ".join(f"requirement-{index}" for index in range(100))

    parts = counter.split(text, budget=30, overlap=5, separators=())

    assert len(parts) > 1
    for previous, current in zip(parts, parts[1:], strict=False):
        bounded_overlap = any(
            current.startswith(previous[-size:])
            and counter.count(previous[-size:]) <= 5
            for size in range(1, min(len(previous), len(current)) + 1)
        )
        assert bounded_overlap


def test_unknown_tokenizer_encoding_is_rejected() -> None:
    with pytest.raises(KnowledgeIndexError, match="KNOWLEDGE_TOKENIZER_ENCODING"):
        TokenCounter("not-a-real-encoding")
