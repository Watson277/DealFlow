from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.documents.pdf.models import BlockIR, DocumentIR, PDFBlockType

PAGE_MARKER = re.compile(r"--- Page (\d+) ---\s*")
TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_index: int
    text: str
    page_number: int | None
    page_end: int | None = None
    section_path: tuple[str, ...] = ()
    block_types: tuple[str, ...] = ()
    source_block_ids: tuple[str, ...] = ()
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class _StructuralUnit:
    page_number: int
    section_path: tuple[str, ...]
    content: str
    block_types: tuple[str, ...]
    block_ids: tuple[str, ...]
    atomic: bool = False


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

    def split(
        self,
        text: str,
        *,
        document_ir: DocumentIR | None = None,
        document_title: str | None = None,
        document_version: str | None = None,
    ) -> list[KnowledgeChunk]:
        if document_ir is not None:
            chunks = self._split_document_ir(
                document_ir,
                document_title=document_title,
                document_version=document_version,
            )
            if chunks:
                return chunks
        return self._split_plain_text(text)

    def _split_document_ir(
        self,
        document_ir: DocumentIR,
        *,
        document_title: str | None,
        document_version: str | None,
    ) -> list[KnowledgeChunk]:
        units = self._structural_units(document_ir)
        chunks: list[KnowledgeChunk] = []
        pending: _StructuralUnit | None = None

        def emit(unit: _StructuralUnit) -> None:
            for content in self._split_unit(unit):
                chunk_text = self._with_context(
                    content,
                    document_title=document_title,
                    document_version=document_version,
                    section_path=unit.section_path,
                )
                chunks.append(
                    KnowledgeChunk(
                        chunk_index=len(chunks),
                        text=chunk_text,
                        page_number=unit.page_number,
                        page_end=unit.page_number,
                        section_path=unit.section_path,
                        block_types=unit.block_types,
                        source_block_ids=unit.block_ids,
                        parent_id=self._parent_id(unit.section_path, unit.page_number),
                    )
                )

        for unit in units:
            if unit.block_types == (PDFBlockType.CAPTION.value,):
                if pending is not None:
                    emit(pending)
                pending = unit
                continue
            if unit.atomic:
                if pending is not None:
                    if (
                        pending.page_number == unit.page_number
                        and pending.section_path == unit.section_path
                        and pending.block_types == (PDFBlockType.CAPTION.value,)
                    ):
                        unit = _StructuralUnit(
                            page_number=unit.page_number,
                            section_path=unit.section_path,
                            content=f"{pending.content}\n\n{unit.content}",
                            block_types=(*pending.block_types, *unit.block_types),
                            block_ids=(*pending.block_ids, *unit.block_ids),
                            atomic=True,
                        )
                    else:
                        emit(pending)
                    pending = None
                emit(unit)
                continue
            if pending is None:
                pending = unit
                continue
            combined = f"{pending.content}\n\n{unit.content}"
            same_context = (
                pending.page_number == unit.page_number
                and pending.section_path == unit.section_path
            )
            if same_context and len(combined) <= self.chunk_size:
                pending = _StructuralUnit(
                    page_number=pending.page_number,
                    section_path=pending.section_path,
                    content=combined,
                    block_types=self._ordered_unique(
                        (*pending.block_types, *unit.block_types)
                    ),
                    block_ids=(*pending.block_ids, *unit.block_ids),
                )
            else:
                emit(pending)
                pending = unit
        if pending is not None:
            emit(pending)
        return chunks

    @staticmethod
    def _structural_units(document_ir: DocumentIR) -> list[_StructuralUnit]:
        units: list[_StructuralUnit] = []
        headings: dict[int, str] = {}
        for page in document_ir.pages:
            for block in sorted(page.blocks, key=lambda item: item.reading_order):
                if block.type in {PDFBlockType.HEADER, PDFBlockType.FOOTER}:
                    continue
                content = KnowledgeChunker._block_content(block)
                if block.type is PDFBlockType.TITLE:
                    if content:
                        level = KnowledgeChunker._heading_level(block)
                        headings = {
                            heading_level: heading
                            for heading_level, heading in headings.items()
                            if heading_level < level
                        }
                        headings[level] = content
                    continue
                if not content:
                    continue
                units.append(
                    _StructuralUnit(
                        page_number=page.page_number,
                        section_path=tuple(headings[level] for level in sorted(headings)),
                        content=content,
                        block_types=(block.type.value,),
                        block_ids=(block.block_id,),
                        atomic=block.type
                        in {PDFBlockType.TABLE, PDFBlockType.FORMULA, PDFBlockType.IMAGE},
                    )
                )
        return units

    @staticmethod
    def _block_content(block: BlockIR) -> str:
        if block.type is PDFBlockType.TABLE and block.table_markdown:
            return block.table_markdown.strip()
        if block.type is PDFBlockType.FORMULA and block.latex:
            return block.latex.strip()
        return (block.text or "").strip()

    @staticmethod
    def _heading_level(block: BlockIR) -> int:
        value = block.metadata.get("heading_level")
        return value if isinstance(value, int) and 1 <= value <= 6 else 3

    def _split_unit(self, unit: _StructuralUnit) -> list[str]:
        if len(unit.content) <= self.chunk_size:
            return [unit.content]
        if PDFBlockType.TABLE.value in unit.block_types:
            table_parts = self._split_markdown_table(unit.content)
            if table_parts is not None:
                return table_parts
        return self._split_section(unit.content)

    def _split_markdown_table(self, table: str) -> list[str] | None:
        lines = [line.strip() for line in table.splitlines() if line.strip()]
        separator_index = next(
            (index for index, line in enumerate(lines[1:], start=1) if TABLE_SEPARATOR.match(line)),
            None,
        )
        if separator_index is None or separator_index + 1 >= len(lines):
            return None
        header = lines[: separator_index + 1]
        rows = lines[separator_index + 1 :]
        chunks: list[str] = []
        current = [*header]
        for row in rows:
            candidate = "\n".join([*current, row])
            if len(candidate) <= self.chunk_size or len(current) == len(header):
                current.append(row)
                continue
            chunks.append("\n".join(current))
            current = [*header, row]
        if len(current) > len(header):
            chunks.append("\n".join(current))
        return chunks or None

    @staticmethod
    def _with_context(
        content: str,
        *,
        document_title: str | None,
        document_version: str | None,
        section_path: tuple[str, ...],
    ) -> str:
        context: list[str] = []
        if document_title and document_title.strip():
            context.append(f"Document: {document_title.strip()}")
        if document_version and document_version.strip():
            context.append(f"Version: {document_version.strip()}")
        if section_path:
            context.append(f"Section: {' > '.join(section_path)}")
        return f"{chr(10).join(context)}\n\n{content}" if context else content

    @staticmethod
    def _parent_id(section_path: tuple[str, ...], page_number: int) -> str:
        identity = " > ".join(section_path).casefold() if section_path else f"page:{page_number}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return f"section:{digest}"

    @staticmethod
    def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    def _split_plain_text(self, text: str) -> list[KnowledgeChunk]:
        sections = self._page_sections(text)
        chunks: list[KnowledgeChunk] = []
        for page_number, section in sections:
            for content in self._split_section(section):
                chunks.append(
                    KnowledgeChunk(
                        chunk_index=len(chunks),
                        text=content,
                        page_number=page_number,
                        page_end=page_number,
                        parent_id=(
                            self._parent_id((), page_number) if page_number is not None else None
                        ),
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
