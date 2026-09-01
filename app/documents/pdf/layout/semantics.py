"""Semantic classification rules for positioned PDF text blocks."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import cast

from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.layout.geometry import height
from app.documents.pdf.models import BlockIR, PDFBlockType

_LIST_PATTERN = re.compile(
    r"^\s*(?:[-*•●▪◦\uf0b7]|(?:\d+|[A-Za-z]|[一二三四五六七八九十]+)[.)、])\s*\S+"
)
_HEADING_PATTERN = re.compile(
    r"^\s*(?:\d+(?:\.\d+)+|第[一二三四五六七八九十百\d]+[章节部分篇]|"
    r"[一二三四五六七八九十]+[、.])\s*\S+"
)
_CAPTION_PATTERN = re.compile(
    r"^\s*(?:图|表)\s*[一二三四五六七八九十百\d]+(?:[-.:：．]\d+)*|"
    r"^\s*(?:figure|table)\s*\d+",
    flags=re.IGNORECASE,
)
_PAGE_NUMBER_PATTERN = re.compile(
    r"^\s*(?:第\s*)?\d+\s*(?:页)?(?:\s*[/／|]\s*(?:共\s*)?\d+\s*(?:页)?)?\s*$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SemanticContext:
    body_font_size: float | None
    body_line_height: float
    repeated_region_keys: frozenset[str]


def build_context(
    blocks: list[BlockIR],
    *,
    repeated_region_keys: frozenset[str],
) -> SemanticContext:
    text_blocks = [block for block in blocks if block.text and block.type is PDFBlockType.TEXT]
    font_sizes = [size for block in text_blocks if (size := block_font_size(block)) is not None]
    line_heights = [height(block.bbox) for block in text_blocks if height(block.bbox) > 0]
    return SemanticContext(
        body_font_size=statistics.median(font_sizes) if font_sizes else None,
        body_line_height=statistics.median(line_heights) if line_heights else 12.0,
        repeated_region_keys=repeated_region_keys,
    )


def classify_text_block(
    block: BlockIR,
    *,
    page_width: float,
    page_height: float,
    context: SemanticContext,
    config: PDFParsingConfig,
) -> BlockIR:
    if block.type is not PDFBlockType.TEXT or not block.text:
        return block

    text = block.text.strip()
    metadata = dict(block.metadata)
    region_key = normalize_repeated_text(text)
    top_region = block.bbox.y0 <= page_height * config.layout_header_footer_margin_ratio
    bottom_region = block.bbox.y1 >= page_height * (1.0 - config.layout_header_footer_margin_ratio)

    block_type = PDFBlockType.TEXT
    if region_key in context.repeated_region_keys and top_region:
        block_type = PDFBlockType.HEADER
    elif (region_key in context.repeated_region_keys and bottom_region) or (
        bottom_region and is_page_number(text)
    ):
        block_type = PDFBlockType.FOOTER
    elif _CAPTION_PATTERN.search(text):
        block_type = PDFBlockType.CAPTION
    elif _is_title(
        block,
        text=text,
        page_width=page_width,
        context=context,
        config=config,
    ):
        block_type = PDFBlockType.TITLE
        metadata["heading_level"] = heading_level(text, block, context)
    elif _LIST_PATTERN.search(text):
        block_type = PDFBlockType.LIST
    elif bottom_region and _is_small_text(block, context):
        block_type = PDFBlockType.FOOTNOTE

    metadata["layout_semantic"] = block_type.value
    return block.model_copy(update={"type": block_type, "metadata": metadata})


def normalize_repeated_text(text: str) -> str:
    normalized = re.sub(r"\d+", "#", text.casefold())
    normalized = re.sub(r"\s+", " ", normalized).strip(" -_|/\\")
    return normalized if 1 < len(normalized) <= 160 else ""


def is_page_number(text: str) -> bool:
    return bool(_PAGE_NUMBER_PATTERN.fullmatch(text))


def block_font_size(block: BlockIR) -> float | None:
    values = block.metadata.get("font_sizes")
    if not isinstance(values, list):
        return None
    numeric = [float(value) for value in values if isinstance(value, (int, float)) and value > 0]
    return max(numeric) if numeric else None


def heading_level(text: str, block: BlockIR, context: SemanticContext) -> int:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", text)
    if match:
        return min(6, match.group(1).count(".") + 1)
    if re.match(r"^\s*第.+[篇章]", text):
        return 1
    if re.match(r"^\s*第.+[节部分]", text):
        return 2
    font_size = block_font_size(block)
    if font_size is not None and context.body_font_size:
        ratio = font_size / context.body_font_size
        if ratio >= 1.7:
            return 1
        if ratio >= 1.4:
            return 2
    return 3


def _is_title(
    block: BlockIR,
    *,
    text: str,
    page_width: float,
    context: SemanticContext,
    config: PDFParsingConfig,
) -> bool:
    if len(text) > 160 or text.count("\n") > 1:
        return False
    font_size = block_font_size(block)
    font_ratio = (
        font_size / context.body_font_size
        if font_size is not None and context.body_font_size
        else 1.0
    )
    height_ratio = height(block.bbox) / max(context.body_line_height, 1.0)
    centered = abs((block.bbox.x0 + block.bbox.x1) / 2.0 - page_width / 2.0) <= page_width * 0.12
    is_bold = bool(block.metadata.get("is_bold"))
    numbered_heading = bool(_HEADING_PATTERN.search(text))
    prominent = font_ratio >= config.layout_title_font_ratio or (
        "\n" not in text and height_ratio >= config.layout_title_font_ratio
    )
    return (numbered_heading and is_bold) or (
        prominent and (is_bold or centered or numbered_heading or len(text) <= 80)
    )


def _is_small_text(block: BlockIR, context: SemanticContext) -> bool:
    font_size = block_font_size(block)
    if font_size is not None and context.body_font_size:
        return font_size < context.body_font_size * 0.85
    return height(block.bbox) < context.body_line_height * 0.85


def semantic_counts(blocks: tuple[BlockIR, ...]) -> dict[str, JsonValue]:
    counts: dict[str, int] = {}
    for block in blocks:
        counts[block.type.value] = counts.get(block.type.value, 0) + 1
    return cast(dict[str, JsonValue], counts)
