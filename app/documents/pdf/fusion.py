"""Cross-channel block deduplication and conflict arbitration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.layout.geometry import (
    first_box_overlap,
    intersection_over_union,
    smaller_box_overlap,
)
from app.documents.pdf.models import BlockIR, PDFBlockSource, PDFBlockType


@dataclass(frozen=True, slots=True)
class BlockFusionResult:
    blocks: tuple[BlockIR, ...]
    duplicate_blocks_removed: int
    table_text_blocks_removed: int
    conflicts_resolved: int


class BlockFusion:
    """Fuse native, OCR, table, and image outputs into one unique block set."""

    version = "bbox-text-fusion-1.0"

    def __init__(self, config: PDFParsingConfig) -> None:
        self.config = config

    def fuse(self, blocks: list[BlockIR] | tuple[BlockIR, ...]) -> BlockFusionResult:
        without_table_text, table_text_removed = self._remove_text_inside_tables(list(blocks))
        retained: list[BlockIR] = []
        duplicates_removed = 0
        conflicts_resolved = 0
        for block in without_table_text:
            duplicate_index = self._duplicate_index(block, retained)
            if duplicate_index is None:
                retained.append(block)
                continue
            duplicates_removed += 1
            existing = retained[duplicate_index]
            if _preference(block) > _preference(existing):
                retained[duplicate_index] = _with_fusion_metadata(block, existing)
                conflicts_resolved += 1
            else:
                retained[duplicate_index] = _with_fusion_metadata(existing, block)
                if _preference(block) != _preference(existing):
                    conflicts_resolved += 1
        retained.sort(key=lambda block: (block.bbox.y0, block.bbox.x0, block.reading_order))
        return BlockFusionResult(
            blocks=tuple(retained),
            duplicate_blocks_removed=duplicates_removed,
            table_text_blocks_removed=table_text_removed,
            conflicts_resolved=conflicts_resolved,
        )

    def _remove_text_inside_tables(self, blocks: list[BlockIR]) -> tuple[list[BlockIR], int]:
        tables = [block for block in blocks if block.type is PDFBlockType.TABLE]
        if not tables:
            return blocks, 0
        retained: list[BlockIR] = []
        removed = 0
        for block in blocks:
            if block.type in _TEXT_TYPES and any(
                first_box_overlap(block.bbox, table.bbox)
                >= self.config.fusion_table_text_overlap_threshold
                for table in tables
            ):
                removed += 1
                continue
            retained.append(block)
        return retained, removed

    def _duplicate_index(self, block: BlockIR, retained: list[BlockIR]) -> int | None:
        for index, existing in enumerate(retained):
            if block.type is PDFBlockType.IMAGE and existing.type is PDFBlockType.IMAGE:
                if (
                    intersection_over_union(block.bbox, existing.bbox)
                    >= self.config.fusion_iou_threshold
                ):
                    return index
                continue
            if block.type not in _TEXT_TYPES or existing.type not in _TEXT_TYPES:
                continue
            similarity = _text_similarity(block.text, existing.text)
            spatial_match = (
                intersection_over_union(block.bbox, existing.bbox)
                >= self.config.fusion_iou_threshold
                or smaller_box_overlap(block.bbox, existing.bbox) >= 0.80
            )
            if spatial_match and similarity >= self.config.fusion_text_similarity_threshold:
                return index
        return None


_TEXT_TYPES = {
    PDFBlockType.TITLE,
    PDFBlockType.TEXT,
    PDFBlockType.LIST,
    PDFBlockType.HEADER,
    PDFBlockType.FOOTER,
    PDFBlockType.CAPTION,
    PDFBlockType.FOOTNOTE,
}


def _text_similarity(first: str | None, second: str | None) -> float:
    left = _normalize_text(first)
    right = _normalize_text(second)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    shorter, longer = sorted((left, right), key=len)
    if shorter in longer and len(shorter) / len(longer) >= 0.50:
        return len(shorter) / len(longer)
    return SequenceMatcher(a=left, b=right, autojunk=False).ratio()


def _normalize_text(value: str | None) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", (value or "").casefold())


def _preference(block: BlockIR) -> tuple[int, int, float, int]:
    type_rank = (
        4 if block.type is PDFBlockType.TABLE else 2 if block.type is PDFBlockType.IMAGE else 3
    )
    source_rank = {
        PDFBlockSource.NATIVE: 3,
        PDFBlockSource.OCR: 2,
        PDFBlockSource.DERIVED: 1,
    }[block.source]
    content_length = len(block.table_markdown or block.text or "")
    return type_rank, source_rank, block.confidence or 0.0, content_length


def _with_fusion_metadata(retained: BlockIR, discarded: BlockIR) -> BlockIR:
    metadata = dict(retained.metadata)
    existing = metadata.get("fusion_discarded_block_ids", [])
    discarded_ids = list(existing) if isinstance(existing, list) else []
    discarded_ids.append(discarded.block_id)
    metadata.update(
        {
            "fusion_version": BlockFusion.version,
            "fusion_discarded_block_ids": discarded_ids,
        }
    )
    return retained.model_copy(update={"metadata": metadata})
