"""Document-level rule-based PDF layout analysis."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.layout.geometry import (
    first_box_overlap,
    height,
    horizontal_overlap_ratio,
    smaller_box_overlap,
    union,
    width,
)
from app.documents.pdf.layout.semantics import (
    block_font_size,
    build_context,
    classify_text_block,
    normalize_repeated_text,
    semantic_counts,
)
from app.documents.pdf.models import (
    BlockIR,
    PageIR,
    ParseWarning,
    PDFBlockSource,
    PDFBlockType,
)


class PDFLayoutAnalyzer:
    version = "rule-layout-1.0"

    def __init__(self, config: PDFParsingConfig) -> None:
        self.config = config

    def analyze(self, pages: tuple[PageIR, ...]) -> tuple[PageIR, ...]:
        if not self.config.layout_enabled:
            return pages
        repeated_keys = self._repeated_region_keys(pages)
        return tuple(self._analyze_page(page, repeated_keys) for page in pages)

    def _analyze_page(
        self,
        page: PageIR,
        repeated_keys: frozenset[str],
    ) -> PageIR:
        input_count = len(page.blocks)
        blocks, duplicate_count = _remove_duplicates(list(page.blocks))
        blocks, table_text_count = _remove_text_inside_tables(blocks)
        context = build_context(blocks, repeated_region_keys=repeated_keys)
        blocks = [
            classify_text_block(
                block,
                page_width=page.width,
                page_height=page.height,
                context=context,
                config=self.config,
            )
            for block in blocks
        ]
        blocks, column_count = _assign_columns(blocks, page.width, self.config)
        blocks, merged_count = _merge_paragraphs(blocks, context.body_line_height, self.config)
        blocks, merged_title_count = _merge_titles(blocks)
        ordered = _reading_order(blocks, column_count)
        finalized, block_id_map = _renumber_and_link_captions(
            ordered, page.page_number, page.height
        )
        warnings = _remap_warnings(page.warnings, block_id_map)
        metadata = dict(page.metadata)
        metadata["layout"] = {
            "analyzer_version": self.version,
            "column_count": column_count,
            "input_block_count": input_count,
            "output_block_count": len(finalized),
            "duplicate_blocks_removed": duplicate_count,
            "table_text_blocks_removed": table_text_count,
            "paragraph_blocks_merged": merged_count,
            "title_blocks_merged": merged_title_count,
            "semantic_counts": semantic_counts(finalized),
        }
        values = page.model_dump()
        values.update({"blocks": finalized, "warnings": warnings, "metadata": metadata})
        return PageIR.model_validate(values)

    def _repeated_region_keys(self, pages: tuple[PageIR, ...]) -> frozenset[str]:
        if len(pages) < 2:
            return frozenset()
        occurrences: Counter[str] = Counter()
        for page in pages:
            page_keys: set[str] = set()
            top_limit = page.height * self.config.layout_header_footer_margin_ratio
            bottom_limit = page.height * (1.0 - self.config.layout_header_footer_margin_ratio)
            for block in page.blocks:
                if not block.text or block.type is not PDFBlockType.TEXT:
                    continue
                if block.bbox.y0 <= top_limit or block.bbox.y1 >= bottom_limit:
                    key = normalize_repeated_text(block.text)
                    if key:
                        page_keys.add(key)
            occurrences.update(page_keys)
        minimum = max(
            2,
            math.ceil(len(pages) * self.config.layout_repeated_region_min_fraction),
        )
        return frozenset(key for key, count in occurrences.items() if count >= minimum)


def _remove_duplicates(blocks: list[BlockIR]) -> tuple[list[BlockIR], int]:
    retained: list[BlockIR] = []
    removed = 0
    for block in blocks:
        normalized = _normalized_block_text(block)
        duplicate_index: int | None = None
        if normalized:
            for index, existing in enumerate(retained):
                if _normalized_block_text(existing) != normalized:
                    continue
                if smaller_box_overlap(block.bbox, existing.bbox) >= 0.85:
                    duplicate_index = index
                    break
        if duplicate_index is None:
            retained.append(block)
            continue
        removed += 1
        if _block_preference(block) > _block_preference(retained[duplicate_index]):
            retained[duplicate_index] = block
    return retained, removed


def _remove_text_inside_tables(blocks: list[BlockIR]) -> tuple[list[BlockIR], int]:
    tables = [block for block in blocks if block.type is PDFBlockType.TABLE]
    if not tables:
        return blocks, 0
    retained: list[BlockIR] = []
    removed = 0
    for block in blocks:
        if block.type is PDFBlockType.TEXT and any(
            first_box_overlap(block.bbox, table.bbox) >= 0.50 for table in tables
        ):
            removed += 1
            continue
        retained.append(block)
    return retained, removed


def _assign_columns(
    blocks: list[BlockIR],
    page_width: float,
    config: PDFParsingConfig,
) -> tuple[list[BlockIR], int]:
    eligible = [
        block
        for block in blocks
        if block.type in {PDFBlockType.TEXT, PDFBlockType.LIST, PDFBlockType.FOOTNOTE}
        and width(block.bbox) <= page_width * 0.55
    ]
    separator: float | None = None
    if len(eligible) >= 4:
        by_center = sorted(eligible, key=lambda block: _center_x(block))
        gaps = [
            (_center_x(right) - _center_x(left), index)
            for index, (left, right) in enumerate(zip(by_center, by_center[1:], strict=False))
        ]
        center_gap, split_index = max(gaps, default=(0.0, 0))
        left_group = by_center[: split_index + 1]
        right_group = by_center[split_index + 1 :]
        if (
            center_gap >= page_width * 0.18
            and len(left_group) >= 2
            and len(right_group) >= 2
            and _groups_have_vertical_overlap(left_group, right_group)
        ):
            gutter = min(block.bbox.x0 for block in right_group) - max(
                block.bbox.x1 for block in left_group
            )
            if gutter >= page_width * config.layout_column_gap_ratio:
                separator = (
                    max(block.bbox.x1 for block in left_group)
                    + min(block.bbox.x0 for block in right_group)
                ) / 2.0

    column_count = 2 if separator is not None else 1
    updated: list[BlockIR] = []
    for block in blocks:
        metadata = dict(block.metadata)
        if block.type in {PDFBlockType.HEADER, PDFBlockType.FOOTER}:
            column_index = -1
        elif separator is None:
            column_index = 0
        elif block.bbox.x0 < separator < block.bbox.x1 or width(block.bbox) >= page_width * 0.65:
            column_index = -1
        else:
            column_index = 0 if _center_x(block) < separator else 1
        metadata["column_index"] = column_index
        updated.append(block.model_copy(update={"metadata": metadata}))
    return updated, column_count


def _merge_paragraphs(
    blocks: list[BlockIR],
    body_line_height: float,
    config: PDFParsingConfig,
) -> tuple[list[BlockIR], int]:
    mergeable = [block for block in blocks if block.type in {PDFBlockType.TEXT, PDFBlockType.LIST}]
    fixed = [block for block in blocks if block not in mergeable]
    merged_output: list[BlockIR] = []
    merged_count = 0
    column_indexes = sorted({_column_index(block) for block in mergeable})
    for column_index in column_indexes:
        column_blocks = sorted(
            (block for block in mergeable if _column_index(block) == column_index),
            key=lambda block: (block.bbox.y0, block.bbox.x0),
        )
        if not column_blocks:
            continue
        current = column_blocks[0]
        for following in column_blocks[1:]:
            if _can_merge(current, following, body_line_height, config):
                current = _merge_pair(current, following)
                merged_count += 1
            else:
                merged_output.append(current)
                current = following
        merged_output.append(current)
    return [*fixed, *merged_output], merged_count


def _merge_titles(blocks: list[BlockIR]) -> tuple[list[BlockIR], int]:
    ordered = sorted(blocks, key=_position_key)
    output: list[BlockIR] = []
    merged_count = 0
    for block in ordered:
        if output and _can_merge_titles(output[-1], block):
            output[-1] = _merge_pair(output[-1], block)
            merged_count += 1
        else:
            output.append(block)
    return output, merged_count


def _can_merge_titles(first: BlockIR, second: BlockIR) -> bool:
    if first.type is not PDFBlockType.TITLE or second.type is not PDFBlockType.TITLE:
        return False
    if _column_index(first) != _column_index(second):
        return False
    if first.metadata.get("heading_level") != second.metadata.get("heading_level"):
        return False
    vertical_gap = second.bbox.y0 - first.bbox.y1
    if vertical_gap < -2 or vertical_gap > max(height(first.bbox), height(second.bbox)):
        return False
    first_font = block_font_size(first)
    second_font = block_font_size(second)
    if (
        first_font
        and second_font
        and abs(first_font - second_font) / max(first_font, second_font) > 0.15
    ):
        return False
    center_distance = abs(_center_x(first) - _center_x(second))
    return center_distance <= max(width(first.bbox), width(second.bbox)) * 0.20


def _can_merge(
    first: BlockIR,
    second: BlockIR,
    body_line_height: float,
    config: PDFParsingConfig,
) -> bool:
    if not first.text or not second.text or _column_index(first) != _column_index(second):
        return False
    if "\n" in first.text or "\n" in second.text:
        return False
    if first.type is PDFBlockType.LIST and second.type is PDFBlockType.LIST:
        return False
    if first.type is PDFBlockType.TEXT and second.type is not PDFBlockType.TEXT:
        return False
    vertical_gap = second.bbox.y0 - first.bbox.y1
    line_height = max(body_line_height, height(first.bbox), height(second.bbox), 1.0)
    if vertical_gap < -line_height * 0.20:
        return False
    if vertical_gap > line_height * config.layout_paragraph_gap_multiplier:
        return False
    aligned = abs(first.bbox.x0 - second.bbox.x0) <= line_height * 1.25
    overlapping = horizontal_overlap_ratio(first.bbox, second.bbox) >= 0.55
    if not (aligned or overlapping):
        return False
    if re.search(r"[。！？.!?]\s*$", first.text) and vertical_gap > line_height * 0.55:
        return False
    first_font = block_font_size(first)
    second_font = block_font_size(second)
    if first_font is None or second_font is None:
        return True
    return abs(first_font - second_font) / max(first_font, second_font) <= 0.20


def _merge_pair(first: BlockIR, second: BlockIR) -> BlockIR:
    first_origins = first.metadata.get("layout_merged_from")
    origins: list[JsonValue] = (
        list(first_origins) if isinstance(first_origins, list) else [first.block_id]
    )
    origins.append(second.block_id)
    metadata = dict(first.metadata)
    metadata.update(
        {
            "layout_merged_from": origins,
            "merged_block_count": len(origins),
        }
    )
    confidences = [value for value in (first.confidence, second.confidence) if value is not None]
    confidence = sum(confidences) / len(confidences) if confidences else None
    source = first.source if first.source is second.source else PDFBlockSource.DERIVED
    return first.model_copy(
        update={
            "bbox": union(first.bbox, second.bbox),
            "source": source,
            "text": _join_text(first.text or "", second.text or ""),
            "raw_text": "\n".join(
                value for value in (first.raw_text, second.raw_text) if value is not None
            ),
            "confidence": round(confidence, 6) if confidence is not None else None,
            "metadata": metadata,
        }
    )


def _reading_order(blocks: list[BlockIR], column_count: int) -> list[BlockIR]:
    headers = sorted(
        (block for block in blocks if block.type is PDFBlockType.HEADER),
        key=_position_key,
    )
    footers = sorted(
        (block for block in blocks if block.type is PDFBlockType.FOOTER),
        key=_position_key,
    )
    main = [block for block in blocks if block not in headers and block not in footers]
    if column_count == 1:
        return [*headers, *sorted(main, key=_position_key), *footers]

    left = sorted((block for block in main if _column_index(block) == 0), key=_position_key)
    right = sorted((block for block in main if _column_index(block) == 1), key=_position_key)
    spanning = sorted((block for block in main if _column_index(block) == -1), key=_position_key)
    ordered: list[BlockIR] = [*headers]
    lower_boundary = float("-inf")
    consumed_left: set[str] = set()
    consumed_right: set[str] = set()
    for spanning_block in spanning:
        for column_blocks, consumed in ((left, consumed_left), (right, consumed_right)):
            band = [
                block
                for block in column_blocks
                if block.block_id not in consumed
                and _center_y(block) >= lower_boundary
                and _center_y(block) < spanning_block.bbox.y0
            ]
            ordered.extend(band)
            consumed.update(block.block_id for block in band)
        ordered.append(spanning_block)
        lower_boundary = max(lower_boundary, spanning_block.bbox.y1)
    ordered.extend(block for block in left if block.block_id not in consumed_left)
    ordered.extend(block for block in right if block.block_id not in consumed_right)
    ordered.extend(footers)
    return ordered


def _renumber_and_link_captions(
    blocks: list[BlockIR],
    page_number: int,
    page_height: float,
) -> tuple[tuple[BlockIR, ...], dict[str, str]]:
    finalized: list[BlockIR] = []
    block_id_map: dict[str, str] = {}
    for index, block in enumerate(blocks, start=1):
        new_id = f"p{page_number}_b{index:04d}"
        block_id_map[block.block_id] = new_id
        origins = block.metadata.get("layout_merged_from")
        if isinstance(origins, list):
            block_id_map.update(
                {str(origin): new_id for origin in origins if isinstance(origin, str)}
            )
        finalized.append(
            block.model_copy(
                update={
                    "block_id": new_id,
                    "reading_order": index - 1,
                }
            )
        )
    targets = [
        block for block in finalized if block.type in {PDFBlockType.IMAGE, PDFBlockType.TABLE}
    ]
    for index, block in enumerate(finalized):
        if block.type is not PDFBlockType.CAPTION:
            continue
        target = _nearest_caption_target(block, targets, page_height)
        if target is None:
            continue
        metadata = dict(block.metadata)
        metadata["caption_for_block_id"] = target.block_id
        finalized[index] = block.model_copy(update={"metadata": metadata})
    return tuple(finalized), block_id_map


def _remap_warnings(
    warnings: tuple[ParseWarning, ...],
    block_id_map: dict[str, str],
) -> tuple[ParseWarning, ...]:
    remapped: list[ParseWarning] = []
    for warning in warnings:
        if warning.block_id is None:
            remapped.append(warning)
            continue
        new_id = block_id_map.get(warning.block_id)
        if new_id is not None:
            remapped.append(warning.model_copy(update={"block_id": new_id}))
            continue
        details = dict(warning.details)
        details["original_block_id"] = warning.block_id
        remapped.append(warning.model_copy(update={"block_id": None, "details": details}))
    return tuple(remapped)


def _nearest_caption_target(
    caption: BlockIR,
    targets: list[BlockIR],
    page_height: float,
) -> BlockIR | None:
    candidates: list[tuple[float, BlockIR]] = []
    for target in targets:
        if horizontal_overlap_ratio(caption.bbox, target.bbox) < 0.20:
            continue
        vertical_distance = min(
            abs(caption.bbox.y0 - target.bbox.y1),
            abs(target.bbox.y0 - caption.bbox.y1),
        )
        if vertical_distance <= page_height * 0.08:
            candidates.append((vertical_distance, target))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _groups_have_vertical_overlap(left: list[BlockIR], right: list[BlockIR]) -> bool:
    left_range = (min(block.bbox.y0 for block in left), max(block.bbox.y1 for block in left))
    right_range = (min(block.bbox.y0 for block in right), max(block.bbox.y1 for block in right))
    overlap = max(0.0, min(left_range[1], right_range[1]) - max(left_range[0], right_range[0]))
    smaller_height = min(left_range[1] - left_range[0], right_range[1] - right_range[0])
    return smaller_height > 0 and overlap / smaller_height >= 0.20


def _normalized_block_text(block: BlockIR) -> str:
    return re.sub(r"\s+", " ", (block.text or "").casefold()).strip()


def _block_preference(block: BlockIR) -> tuple[int, float]:
    source_rank = {
        PDFBlockSource.NATIVE: 3,
        PDFBlockSource.OCR: 2,
        PDFBlockSource.DERIVED: 1,
    }[block.source]
    return source_rank, block.confidence or 0.0


def _column_index(block: BlockIR) -> int:
    value = block.metadata.get("column_index", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _center_x(block: BlockIR) -> float:
    return (block.bbox.x0 + block.bbox.x1) / 2.0


def _center_y(block: BlockIR) -> float:
    return (block.bbox.y0 + block.bbox.y1) / 2.0


def _position_key(block: BlockIR) -> tuple[float, float]:
    return block.bbox.y0, block.bbox.x0


def _join_text(first: str, second: str) -> str:
    if first.endswith("-") and second[:1].isalnum():
        return first[:-1] + second
    if first and second and _is_cjk(first[-1]) and _is_cjk(second[0]):
        return first + second
    return f"{first} {second}".strip()


def _is_cjk(character: str) -> bool:
    name = unicodedata.name(character, "")
    return any(script in name for script in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL"))
