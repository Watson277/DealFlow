import re
from dataclasses import dataclass

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError

PAGE_MARKER = re.compile(r"--- Page (\d+) ---\s*")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_index: int
    text: str
    page_number: int | None


class KnowledgeChunker:
    def __init__(self, settings: Settings) -> None:
        self.chunk_size = settings.knowledge_chunk_size_chars
        self.overlap = settings.knowledge_chunk_overlap_chars
        if self.chunk_size < 1:
            raise KnowledgeIndexError("KNOWLEDGE_CHUNK_SIZE_CHARS must be positive")
        if self.overlap < 0 or self.overlap >= self.chunk_size:
            raise KnowledgeIndexError(
                "KNOWLEDGE_CHUNK_OVERLAP_CHARS must be between zero and chunk size"
            )

    def split(self, text: str) -> list[KnowledgeChunk]:
        sections = self._page_sections(text)
        chunks: list[KnowledgeChunk] = []
        for page_number, section in sections:
            for content in self._split_section(section):
                chunks.append(
                    KnowledgeChunk(
                        chunk_index=len(chunks),
                        text=content,
                        page_number=page_number,
                    )
                )
        if not chunks:
            raise KnowledgeIndexError("knowledge document contains no indexable text")
        return chunks

    @staticmethod
    def _page_sections(text: str) -> list[tuple[int | None, str]]:
        matches = list(PAGE_MARKER.finditer(text))
        if not matches:
            return [(None, text.strip())] if text.strip() else []
        sections: list[tuple[int | None, str]] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                sections.append((int(match.group(1)), content))
        return sections

    def _split_section(self, text: str) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            proposed_end = min(start + self.chunk_size, len(text))
            end = proposed_end
            if proposed_end < len(text):
                boundary = text.rfind("\n\n", start, proposed_end)
                if boundary > start + self.chunk_size // 2:
                    end = boundary
            content = text[start:end].strip()
            if content:
                chunks.append(content)
            if end >= len(text):
                break
            start = max(end - self.overlap, start + 1)
        return chunks
