from __future__ import annotations

from functools import lru_cache

import tiktoken
from tiktoken import Encoding

from app.core.exceptions import KnowledgeIndexError


class TokenCounter:
    """Count and split text with one deterministic, configurable tokenizer."""

    def __init__(self, encoding_name: str) -> None:
        self.encoding_name = encoding_name
        try:
            self.encoding = _encoding(encoding_name)
        except ValueError as exc:
            raise KnowledgeIndexError(
                f"unknown KNOWLEDGE_TOKENIZER_ENCODING: {encoding_name}"
            ) from exc

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text, disallowed_special=()))

    def split(
        self,
        text: str,
        *,
        budget: int,
        overlap: int = 0,
        separators: tuple[str, ...] = ("\n\n", "。", ". ", "\n"),
    ) -> list[str]:
        if budget < 1:
            raise KnowledgeIndexError("token budget must be positive")
        if overlap < 0 or overlap >= budget:
            raise KnowledgeIndexError("token overlap must be between zero and token budget")
        normalized = text.strip()
        if not normalized:
            return []
        if self.count(normalized) <= budget:
            return [normalized]

        parts: list[str] = []
        start = 0
        while start < len(normalized):
            maximum_end = self._maximum_end(normalized, start, budget)
            if maximum_end >= len(normalized):
                content = normalized[start:].strip()
                if content:
                    parts.append(content)
                break

            end = self._semantic_end(
                normalized,
                start=start,
                maximum_end=maximum_end,
                budget=budget,
                separators=separators,
            )
            content = normalized[start:end].strip()
            if content:
                parts.append(content)
            next_start = self._overlap_start(normalized, start, end, overlap)
            start = max(next_start, start + 1)
        return parts

    def _maximum_end(self, text: str, start: int, budget: int) -> int:
        low = start + 1
        high = len(text)
        best = start + 1
        while low <= high:
            middle = (low + high) // 2
            if self.count(text[start:middle]) <= budget:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        return best

    def _semantic_end(
        self,
        text: str,
        *,
        start: int,
        maximum_end: int,
        budget: int,
        separators: tuple[str, ...],
    ) -> int:
        for separator in separators:
            boundary = text.rfind(separator, start, maximum_end)
            candidate = boundary + len(separator)
            if boundary > start and self.count(text[start:candidate]) >= budget // 2:
                return candidate
        return maximum_end

    def _overlap_start(self, text: str, start: int, end: int, overlap: int) -> int:
        if overlap == 0:
            return end
        low = start
        high = end
        best = end
        while low <= high:
            middle = (low + high) // 2
            if self.count(text[middle:end]) <= overlap:
                best = middle
                high = middle - 1
            else:
                low = middle + 1
        return best


@lru_cache(maxsize=16)
def _encoding(name: str) -> Encoding:
    return tiktoken.get_encoding(name)
