"""Source-neutral structural documents and hierarchical knowledge chunks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.documents.pdf.models import BlockIR, DocumentIR, PDFBlockType
from app.rag.markdown import MarkdownUnit, parse_markdown_units

NodeType: TypeAlias = Literal[
    "heading",
    "paragraph",
    "list",
    "table",
    "code",
    "image",
    "formula",
    "caption",
    "footnote",
]
SourceType: TypeAlias = Literal["pdf", "markdown", "docx"]

_TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
_FENCE_START = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


class ChunkIRModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LocatedBoundingBox(ChunkIRModel):
    page: int = Field(ge=1)
    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)


class PDFSourceLocation(ChunkIRModel):
    source_type: Literal["pdf"] = "pdf"
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    block_ids: tuple[str, ...] = ()
    bboxes: tuple[LocatedBoundingBox, ...] = ()


class MarkdownSourceLocation(ChunkIRModel):
    source_type: Literal["markdown"] = "markdown"
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    block_ids: tuple[str, ...] = ()


class DocxSourceLocation(ChunkIRModel):
    source_type: Literal["docx"] = "docx"
    paragraph_start: int = Field(ge=1)
    paragraph_end: int = Field(ge=1)
    block_ids: tuple[str, ...] = ()


SourceLocation: TypeAlias = Annotated[
    PDFSourceLocation | MarkdownSourceLocation | DocxSourceLocation,
    Field(discriminator="source_type"),
]


class StructuralNode(ChunkIRModel):
    node_id: str
    node_type: NodeType
    text: str = Field(min_length=1)
    section_path: tuple[str, ...] = ()
    order: int = Field(ge=0)
    location: SourceLocation
    atomic: bool = False


class StructuralDocument(ChunkIRModel):
    document_id: str
    source_type: SourceType
    title: str | None = None
    version: str | None = None
    nodes: tuple[StructuralNode, ...]


class ParentChunk(ChunkIRModel):
    chunk_id: str
    document_id: str
    chunk_level: Literal["parent"] = "parent"
    text: str = Field(min_length=1)
    section_path: tuple[str, ...] = ()
    order: int = Field(ge=0)
    source_node_ids: tuple[str, ...]
    block_types: tuple[str, ...]
    location: SourceLocation
    char_count: int = Field(ge=1)
    content_hash: str


class ChildChunk(ChunkIRModel):
    chunk_id: str
    parent_id: str
    document_id: str
    chunk_level: Literal["child"] = "child"
    text: str = Field(min_length=1)
    embedding_text: str = Field(min_length=1)
    section_path: tuple[str, ...] = ()
    order: int = Field(ge=0)
    child_order: int = Field(ge=0)
    source_node_ids: tuple[str, ...]
    block_types: tuple[str, ...]
    location: SourceLocation
    char_count: int = Field(ge=1)
    content_hash: str


class KnowledgeChunkBundle(ChunkIRModel):
    schema_version: Literal["1.0"] = "1.0"
    document_id: str
    source_type: SourceType
    parents: tuple[ParentChunk, ...]
    children: tuple[ChildChunk, ...]


@dataclass(frozen=True, slots=True)
class _ParentDraft:
    nodes: tuple[StructuralNode, ...]


class PDFStructureAdapter:
    """Convert positioned PDF blocks into source-neutral structural nodes."""

    @staticmethod
    def convert(
        document_ir: DocumentIR,
        *,
        document_id: str,
        title: str | None,
        version: str | None,
    ) -> StructuralDocument:
        headings: dict[int, str] = {}
        nodes: list[StructuralNode] = []
        pending_caption: tuple[BlockIR, int] | None = None

        def append_block(
            block: BlockIR,
            page_number: int,
            *,
            prefix_block: tuple[BlockIR, int] | None = None,
        ) -> None:
            content = PDFStructureAdapter._content(block)
            prefix = (
                PDFStructureAdapter._content(prefix_block[0]) if prefix_block is not None else None
            )
            if prefix:
                content = f"{prefix}\n\n{content}" if content else prefix
            if not content:
                return
            block_ids = (
                (prefix_block[0].block_id, block.block_id)
                if prefix_block is not None
                else (block.block_id,)
            )
            bboxes = tuple(
                LocatedBoundingBox(page=located_page, **located_block.bbox.model_dump())
                for located_block, located_page in (
                    (*((prefix_block,) if prefix_block is not None else ()), (block, page_number))
                )
            )
            nodes.append(
                StructuralNode(
                    node_id=block.block_id,
                    node_type=PDFStructureAdapter._node_type(block.type),
                    text=content,
                    section_path=tuple(headings[level] for level in sorted(headings)),
                    order=len(nodes),
                    location=PDFSourceLocation(
                        page_start=page_number,
                        page_end=page_number,
                        block_ids=block_ids,
                        bboxes=bboxes,
                    ),
                    atomic=block.type
                    in {PDFBlockType.TABLE, PDFBlockType.IMAGE, PDFBlockType.FORMULA},
                )
            )

        for page in document_ir.pages:
            for block in sorted(page.blocks, key=lambda item: item.reading_order):
                if block.type in {PDFBlockType.HEADER, PDFBlockType.FOOTER}:
                    continue
                content = PDFStructureAdapter._content(block)
                if block.type is PDFBlockType.TITLE:
                    if content:
                        level = PDFStructureAdapter._heading_level(block)
                        headings = {
                            existing_level: heading
                            for existing_level, heading in headings.items()
                            if existing_level < level
                        }
                        headings[level] = content
                    continue
                if block.type is PDFBlockType.CAPTION:
                    if pending_caption is not None:
                        append_block(pending_caption[0], pending_caption[1])
                    pending_caption = (block, page.page_number)
                    continue
                if pending_caption is not None:
                    caption, caption_page = pending_caption
                    if block.type in {PDFBlockType.TABLE, PDFBlockType.IMAGE}:
                        append_block(
                            block,
                            page.page_number,
                            prefix_block=(caption, caption_page),
                        )
                        pending_caption = None
                        continue
                    append_block(caption, caption_page)
                    pending_caption = None
                append_block(block, page.page_number)
        if pending_caption is not None:
            append_block(pending_caption[0], pending_caption[1])
        return StructuralDocument(
            document_id=document_id,
            source_type="pdf",
            title=_clean_optional(title),
            version=_clean_optional(version),
            nodes=tuple(nodes),
        )

    @staticmethod
    def _content(block: BlockIR) -> str:
        if block.type is PDFBlockType.TABLE and block.table_markdown:
            return block.table_markdown.strip()
        if block.type is PDFBlockType.FORMULA and block.latex:
            return block.latex.strip()
        return (block.text or "").strip()

    @staticmethod
    def _heading_level(block: BlockIR) -> int:
        value = block.metadata.get("heading_level")
        return value if isinstance(value, int) and 1 <= value <= 6 else 3

    @staticmethod
    def _node_type(block_type: PDFBlockType) -> NodeType:
        mapping: dict[PDFBlockType, NodeType] = {
            PDFBlockType.TEXT: "paragraph",
            PDFBlockType.LIST: "list",
            PDFBlockType.TABLE: "table",
            PDFBlockType.IMAGE: "image",
            PDFBlockType.FORMULA: "formula",
            PDFBlockType.CAPTION: "caption",
            PDFBlockType.FOOTNOTE: "footnote",
            PDFBlockType.TITLE: "heading",
            PDFBlockType.HEADER: "paragraph",
            PDFBlockType.FOOTER: "paragraph",
        }
        return mapping[block_type]


class MarkdownStructureAdapter:
    """Convert Markdown blocks and line spans into source-neutral nodes."""

    @staticmethod
    def convert(
        text: str,
        *,
        document_id: str,
        title: str | None,
        version: str | None,
    ) -> StructuralDocument:
        nodes = tuple(
            StructuralNode(
                node_id=unit.block_id,
                node_type=MarkdownStructureAdapter._node_type(unit),
                text=unit.content,
                section_path=unit.section_path,
                order=index,
                location=MarkdownSourceLocation(
                    line_start=unit.line_start,
                    line_end=unit.line_end,
                    block_ids=(unit.block_id,),
                ),
                atomic=unit.atomic,
            )
            for index, unit in enumerate(parse_markdown_units(text))
        )
        return StructuralDocument(
            document_id=document_id,
            source_type="markdown",
            title=_clean_optional(title),
            version=_clean_optional(version),
            nodes=nodes,
        )

    @staticmethod
    def _node_type(unit: MarkdownUnit) -> NodeType:
        value = unit.block_type.split("+", maxsplit=1)[0]
        return {
            "text": "paragraph",
            "list": "list",
            "table": "table",
            "code": "code",
        }.get(value, "paragraph")  # type: ignore[return-value]


class DocxStructureAdapter:
    """Keep DOCX compatible by representing extracted paragraphs structurally."""

    @staticmethod
    def convert(
        text: str,
        *,
        document_id: str,
        title: str | None,
        version: str | None,
    ) -> StructuralDocument:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n|\n", text) if item.strip()]
        nodes = tuple(
            StructuralNode(
                node_id=f"docx_b{index:04d}",
                node_type="paragraph",
                text=paragraph,
                order=index - 1,
                location=DocxSourceLocation(
                    paragraph_start=index,
                    paragraph_end=index,
                    block_ids=(f"docx_b{index:04d}",),
                ),
            )
            for index, paragraph in enumerate(paragraphs, start=1)
        )
        return StructuralDocument(
            document_id=document_id,
            source_type="docx",
            title=_clean_optional(title),
            version=_clean_optional(version),
            nodes=nodes,
        )


class HierarchicalKnowledgeChunker:
    """Build semantic parents and retrieval-sized children from structural nodes."""

    def __init__(self, settings: Settings) -> None:
        self.parent_size = settings.knowledge_parent_chunk_size_chars
        self.child_size = settings.knowledge_child_chunk_size_chars
        self.overlap = settings.knowledge_child_overlap_chars
        if self.parent_size < self.child_size:
            raise KnowledgeIndexError("parent chunk size must be at least child chunk size")
        if self.overlap < 0 or self.overlap >= self.child_size:
            raise KnowledgeIndexError("child overlap must be between zero and child size")

    def split(self, document: StructuralDocument) -> KnowledgeChunkBundle:
        if not document.nodes:
            raise KnowledgeIndexError("knowledge document contains no structural content")
        drafts = self._parent_drafts(document.nodes)
        parents: list[ParentChunk] = []
        children: list[ChildChunk] = []
        for parent_order, draft in enumerate(drafts):
            parent = self._parent(document, draft, parent_order)
            parents.append(parent)
            for child_order, (text, nodes) in enumerate(self._child_drafts(draft.nodes)):
                children.append(
                    self._child(
                        document,
                        parent,
                        text,
                        nodes,
                        order=len(children),
                        child_order=child_order,
                    )
                )
        if not children:
            raise KnowledgeIndexError("knowledge document produced no child chunks")
        return KnowledgeChunkBundle(
            document_id=document.document_id,
            source_type=document.source_type,
            parents=tuple(parents),
            children=tuple(children),
        )

    def _parent_drafts(self, nodes: tuple[StructuralNode, ...]) -> list[_ParentDraft]:
        drafts: list[_ParentDraft] = []
        pending: list[StructuralNode] = []

        def flush() -> None:
            if pending:
                drafts.append(_ParentDraft(nodes=tuple(pending)))
                pending.clear()

        for node in nodes:
            if node.atomic:
                flush()
                drafts.append(_ParentDraft(nodes=(node,)))
                continue
            candidate_size = len(node.text) + sum(len(item.text) + 2 for item in pending)
            if pending and (
                pending[-1].section_path != node.section_path
                or candidate_size > self.parent_size
            ):
                flush()
            pending.append(node)
        flush()
        return drafts

    def _parent(
        self,
        document: StructuralDocument,
        draft: _ParentDraft,
        order: int,
    ) -> ParentChunk:
        text = "\n\n".join(node.text for node in draft.nodes).strip()
        section_path = draft.nodes[0].section_path
        identity = f"dealflow:{document.document_id}:parent:{order}:{' > '.join(section_path)}"
        return ParentChunk(
            chunk_id=str(uuid5(NAMESPACE_URL, identity)),
            document_id=document.document_id,
            text=text,
            section_path=section_path,
            order=order,
            source_node_ids=_ordered_unique(
                tuple(node.node_id for node in draft.nodes)
            ),
            block_types=_ordered_unique(
                tuple(node.node_type for node in draft.nodes)
            ),
            location=_merge_locations(draft.nodes),
            char_count=len(text),
            content_hash=_content_hash(text),
        )

    def _child_drafts(
        self, nodes: tuple[StructuralNode, ...]
    ) -> list[tuple[str, tuple[StructuralNode, ...]]]:
        if len(nodes) == 1 and nodes[0].atomic:
            return [(part, nodes) for part in self._split_atomic(nodes[0])]

        drafts: list[tuple[str, tuple[StructuralNode, ...]]] = []
        pending: list[StructuralNode] = []

        def flush() -> None:
            if pending:
                drafts.append(("\n\n".join(node.text for node in pending), tuple(pending)))
                pending.clear()

        for node in nodes:
            if len(node.text) > self.child_size:
                flush()
                drafts.extend((part, (node,)) for part in self._split_text(node.text))
                continue
            candidate_size = len(node.text) + sum(len(item.text) + 2 for item in pending)
            if pending and candidate_size > self.child_size:
                flush()
            pending.append(node)
        flush()
        return drafts

    def _split_atomic(self, node: StructuralNode) -> list[str]:
        if len(node.text) <= self.child_size:
            return [node.text]
        if node.node_type == "table":
            table_parts = self._split_table(node.text)
            if table_parts:
                return table_parts
        if node.node_type == "code":
            code_parts = self._split_code(node.text)
            if code_parts:
                return code_parts
        return self._split_text(node.text)

    def _split_table(self, table: str) -> list[str] | None:
        lines = [line.strip() for line in table.splitlines() if line.strip()]
        separator_index = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if _TABLE_SEPARATOR.match(line)
            ),
            None,
        )
        if separator_index is None or separator_index + 1 >= len(lines):
            return None
        header = lines[: separator_index + 1]
        rows = lines[separator_index + 1 :]
        parts: list[str] = []
        current = [*header]
        for row in rows:
            candidate = "\n".join([*current, row])
            if len(candidate) <= self.child_size or len(current) == len(header):
                current.append(row)
            else:
                parts.append("\n".join(current))
                current = [*header, row]
        if len(current) > len(header):
            parts.append("\n".join(current))
        return parts or None

    def _split_code(self, code: str) -> list[str] | None:
        lines = code.splitlines()
        match = _FENCE_START.match(lines[0]) if lines else None
        if match is None:
            return None
        fence = match.group(1)
        has_closing = len(lines) > 1 and lines[-1].lstrip().startswith(fence)
        closing = lines[-1] if has_closing else fence
        body = lines[1:-1] if has_closing else lines[1:]
        parts: list[str] = []
        current: list[str] = []
        for line in body:
            candidate = "\n".join([lines[0], *current, line, closing])
            if len(candidate) <= self.child_size or not current:
                current.append(line)
            else:
                parts.append("\n".join([lines[0], *current, closing]))
                current = [line]
        if current or not parts:
            parts.append("\n".join([lines[0], *current, closing]))
        return parts

    def _split_text(self, text: str) -> list[str]:
        parts: list[str] = []
        start = 0
        while start < len(text):
            proposed_end = min(start + self.child_size, len(text))
            end = proposed_end
            if proposed_end < len(text):
                for separator in ("\n\n", "。", ". ", "\n"):
                    boundary = text.rfind(separator, start, proposed_end)
                    if boundary > start + self.child_size // 2:
                        end = boundary + len(separator)
                        break
            content = text[start:end].strip()
            if content:
                parts.append(content)
            if end >= len(text):
                break
            start = max(end - self.overlap, start + 1)
        return parts

    @staticmethod
    def _child(
        document: StructuralDocument,
        parent: ParentChunk,
        text: str,
        nodes: tuple[StructuralNode, ...],
        *,
        order: int,
        child_order: int,
    ) -> ChildChunk:
        identity = f"dealflow:{parent.chunk_id}:child:{child_order}:{_content_hash(text)}"
        return ChildChunk(
            chunk_id=str(uuid5(NAMESPACE_URL, identity)),
            parent_id=parent.chunk_id,
            document_id=document.document_id,
            text=text,
            embedding_text=_embedding_text(document, parent.section_path, text),
            section_path=parent.section_path,
            order=order,
            child_order=child_order,
            source_node_ids=_ordered_unique(tuple(node.node_id for node in nodes)),
            block_types=_ordered_unique(tuple(node.node_type for node in nodes)),
            location=_merge_locations(nodes),
            char_count=len(text),
            content_hash=_content_hash(text),
        )


KNOWLEDGE_CHUNK_CONTENT_TYPE = "application/json; charset=utf-8"
KNOWLEDGE_CHUNK_FILENAME = "knowledge-chunks.v1.json"


def knowledge_chunk_object_key(document_id: UUID | str) -> str:
    canonical_id = UUID(str(document_id))
    return f"documents/{canonical_id}/chunks/{KNOWLEDGE_CHUNK_FILENAME}"


def serialize_knowledge_chunks(bundle: KnowledgeChunkBundle) -> str:
    payload = bundle.model_dump_json(indent=2)
    KnowledgeChunkBundle.model_validate_json(payload)
    return f"{payload}\n"


def _merge_locations(nodes: tuple[StructuralNode, ...]) -> SourceLocation:
    first = nodes[0].location
    if isinstance(first, PDFSourceLocation):
        pdf_locations = [
            node.location for node in nodes if isinstance(node.location, PDFSourceLocation)
        ]
        return PDFSourceLocation(
            page_start=min(item.page_start for item in pdf_locations),
            page_end=max(item.page_end for item in pdf_locations),
            block_ids=_ordered_unique(
                tuple(value for item in pdf_locations for value in item.block_ids)
            ),
            bboxes=tuple(value for item in pdf_locations for value in item.bboxes),
        )
    if isinstance(first, MarkdownSourceLocation):
        markdown_locations = [
            node.location for node in nodes if isinstance(node.location, MarkdownSourceLocation)
        ]
        return MarkdownSourceLocation(
            line_start=min(item.line_start for item in markdown_locations),
            line_end=max(item.line_end for item in markdown_locations),
            block_ids=_ordered_unique(
                tuple(value for item in markdown_locations for value in item.block_ids)
            ),
        )
    docx_locations = [
        node.location for node in nodes if isinstance(node.location, DocxSourceLocation)
    ]
    return DocxSourceLocation(
        paragraph_start=min(item.paragraph_start for item in docx_locations),
        paragraph_end=max(item.paragraph_end for item in docx_locations),
        block_ids=_ordered_unique(
            tuple(value for item in docx_locations for value in item.block_ids)
        ),
    )


def _embedding_text(
    document: StructuralDocument,
    section_path: tuple[str, ...],
    text: str,
) -> str:
    context: list[str] = []
    if document.title:
        context.append(f"Document: {document.title}")
    if document.version:
        context.append(f"Version: {document.version}")
    if section_path:
        context.append(f"Section: {' > '.join(section_path)}")
    return f"{chr(10).join(context)}\n\n{text}" if context else text


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _clean_optional(value: str | None) -> str | None:
    normalized = value.strip() if value else ""
    return normalized or None
