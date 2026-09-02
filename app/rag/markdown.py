"""Lightweight structural parsing for Markdown knowledge documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.rag.chunking import KnowledgeChunk

_ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*)$")
_SETEXT_HEADING = re.compile(r"^ {0,3}(=+|-+)\s*$")
_FENCE_START = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_LIST_ITEM = re.compile(
    r"^\s*(?:[-+*]\s+|\d+[.)]\s+|[-+*]\s+\[[ xX]\]\s+)\S"
)
_TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_HORIZONTAL_RULE = re.compile(r"^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")


@dataclass(frozen=True, slots=True)
class MarkdownUnit:
    """One Markdown block with the heading context active at its position."""

    content: str
    section_path: tuple[str, ...]
    block_type: str
    block_id: str
    atomic: bool = False


class MarkdownKnowledgeChunker:
    """Turn Markdown blocks into embedding-ready knowledge chunks."""

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
        document_title: str | None = None,
        document_version: str | None = None,
    ) -> list[KnowledgeChunk]:
        units = parse_markdown_units(text)
        if not units:
            raise KnowledgeIndexError("knowledge document contains no indexable Markdown")

        grouped = self._group_units(units)
        chunks: list[KnowledgeChunk] = []
        for unit in grouped:
            for content in self._split_unit(unit):
                chunks.append(
                    self._knowledge_chunk(
                        chunk_index=len(chunks),
                        text=_with_context(
                            content,
                            document_title=document_title,
                            document_version=document_version,
                            section_path=unit.section_path,
                        ),
                        unit=unit,
                    )
                )
        return chunks

    def _group_units(self, units: list[MarkdownUnit]) -> list[MarkdownUnit]:
        grouped: list[MarkdownUnit] = []
        pending: MarkdownUnit | None = None
        for unit in units:
            if unit.atomic:
                if pending is not None:
                    grouped.append(pending)
                    pending = None
                grouped.append(unit)
                continue
            if pending is None:
                pending = unit
                continue
            combined = f"{pending.content}\n\n{unit.content}"
            if pending.section_path == unit.section_path and len(combined) <= self.chunk_size:
                pending = MarkdownUnit(
                    content=combined,
                    section_path=pending.section_path,
                    block_type="+".join(
                        dict.fromkeys((pending.block_type, unit.block_type))
                    ),
                    block_id="+".join((pending.block_id, unit.block_id)),
                )
            else:
                grouped.append(pending)
                pending = unit
        if pending is not None:
            grouped.append(pending)
        return grouped

    def _split_unit(self, unit: MarkdownUnit) -> list[str]:
        if len(unit.content) <= self.chunk_size:
            return [unit.content]
        if unit.block_type == "table":
            parts = self._split_table(unit.content)
            if parts:
                return parts
        if unit.block_type == "code":
            parts = self._split_code(unit.content)
            if parts:
                return parts
        return self._split_text(unit.content)

    def _split_table(self, table: str) -> list[str] | None:
        lines = [line.strip() for line in table.splitlines() if line.strip()]
        if len(lines) < 3 or not _is_table_separator(lines[1]):
            return None
        header = lines[:2]
        chunks: list[str] = []
        current = [*header]
        for row in lines[2:]:
            candidate = "\n".join([*current, row])
            if len(candidate) <= self.chunk_size or len(current) == len(header):
                current.append(row)
                continue
            chunks.append("\n".join(current))
            current = [*header, row]
        if len(current) > len(header):
            chunks.append("\n".join(current))
        return chunks or None

    def _split_code(self, code: str) -> list[str] | None:
        lines = code.splitlines()
        if len(lines) < 2:
            return None
        opening_match = _FENCE_START.match(lines[0])
        if opening_match is None:
            return None
        fence = opening_match.group(1)
        closing_pattern = re.compile(
            rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*$"
        )
        has_closing = bool(closing_pattern.match(lines[-1]))
        closing = lines[-1] if has_closing else fence
        body = lines[1:-1] if has_closing else lines[1:]
        chunks: list[str] = []
        current: list[str] = []
        for line in body:
            candidate = "\n".join([lines[0], *current, line, closing])
            if len(candidate) <= self.chunk_size or not current:
                current.append(line)
                continue
            chunks.append("\n".join([lines[0], *current, closing]))
            current = [line]
        if current or not chunks:
            chunks.append("\n".join([lines[0], *current, closing]))
        return chunks

    def _split_text(self, text: str) -> list[str]:
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

    @staticmethod
    def _knowledge_chunk(
        *,
        chunk_index: int,
        text: str,
        unit: MarkdownUnit,
    ) -> KnowledgeChunk:
        values: dict[str, object] = {
            "chunk_index": chunk_index,
            "text": text,
            "page_number": None,
        }
        available_fields = getattr(KnowledgeChunk, "__dataclass_fields__", {})
        optional_values: dict[str, object] = {
            "page_end": None,
            "section_path": unit.section_path,
            "block_types": tuple(unit.block_type.split("+")),
            "source_block_ids": tuple(unit.block_id.split("+")),
            "parent_id": _parent_id(unit.section_path),
        }
        values.update(
            {key: value for key, value in optional_values.items() if key in available_fields}
        )
        factory: Any = KnowledgeChunk
        return cast(KnowledgeChunk, factory(**values))


def parse_markdown_units(text: str) -> list[MarkdownUnit]:
    """Parse headings, tables, code fences, lists, and paragraphs without rendering HTML."""

    lines = text.splitlines()
    units: list[MarkdownUnit] = []
    headings: dict[int, str] = {}
    buffered: list[str] = []
    buffered_type = "text"

    def section_path() -> tuple[str, ...]:
        return tuple(headings[level] for level in sorted(headings))

    def add_unit(content: str, block_type: str, *, atomic: bool = False) -> None:
        normalized = content.strip()
        if not normalized:
            return
        units.append(
            MarkdownUnit(
                content=normalized,
                section_path=section_path(),
                block_type=block_type,
                block_id=f"md_b{len(units) + 1:04d}",
                atomic=atomic,
            )
        )

    def flush() -> None:
        nonlocal buffered, buffered_type
        if buffered:
            add_unit("\n".join(buffered), buffered_type)
        buffered = []
        buffered_type = "text"

    def set_heading(level: int, value: str) -> None:
        heading = _strip_inline_heading_closer(value)
        if not heading:
            return
        for existing_level in tuple(headings):
            if existing_level >= level:
                del headings[existing_level]
        headings[level] = heading

    index = 0
    while index < len(lines):
        line = lines[index]
        fence_match = _FENCE_START.match(line)
        if fence_match:
            flush()
            fence = fence_match.group(1)
            code_lines = [line]
            index += 1
            closing = re.compile(
                rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*$"
            )
            while index < len(lines):
                code_lines.append(lines[index])
                is_closing = bool(closing.match(lines[index]))
                index += 1
                if is_closing:
                    break
            add_unit("\n".join(code_lines), "code", atomic=True)
            continue

        heading_match = _ATX_HEADING.match(line)
        if heading_match:
            flush()
            set_heading(len(heading_match.group(1)), heading_match.group(2))
            index += 1
            continue

        if index + 1 < len(lines) and line.strip():
            setext_match = _SETEXT_HEADING.match(lines[index + 1])
            if setext_match:
                flush()
                set_heading(1 if setext_match.group(1).startswith("=") else 2, line.strip())
                index += 2
                continue

        if _starts_markdown_table(lines, index):
            flush()
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                table_lines.append(lines[index])
                index += 1
            add_unit("\n".join(table_lines), "table", atomic=True)
            continue

        if not line.strip():
            flush()
            index += 1
            continue

        if _HORIZONTAL_RULE.match(line):
            flush()
            index += 1
            continue

        line_type = "list" if _LIST_ITEM.match(line) else "text"
        if buffered and line_type != buffered_type:
            flush()
        buffered_type = line_type
        buffered.append(line)
        index += 1

    flush()
    return units


def _starts_markdown_table(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return False
    cells = _table_cells(lines[index + 1])
    return bool(cells) and all(_TABLE_SEPARATOR_CELL.fullmatch(cell) for cell in cells)


def _table_cells(line: str) -> list[str]:
    normalized = line.strip().strip("|")
    if "|" not in normalized:
        return []
    return [cell.strip().replace(" ", "") for cell in normalized.split("|")]


def _strip_inline_heading_closer(value: str) -> str:
    return re.sub(r"[ \t]+#+[ \t]*$", "", value).strip()


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(_TABLE_SEPARATOR_CELL.fullmatch(cell) for cell in cells)


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


def _parent_id(section_path: tuple[str, ...]) -> str:
    identity = " > ".join(section_path).casefold() if section_path else "document"
    digest = sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"section:{digest}"
