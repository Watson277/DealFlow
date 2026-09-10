"""Page-level text quality and content-type classification."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.models import PDFPageType

BBoxTuple = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PageQuality:
    page_type: PDFPageType
    confidence: float
    requires_ocr: bool
    effective_char_count: int
    word_count: int
    garbled_char_count: int
    garbled_ratio: float
    text_coverage: float
    image_coverage: float
    significant_image_count: int
    significant_image_coverage: float
    largest_image_area_ratio: float

    def as_metadata(self) -> dict[str, JsonValue]:
        return {
            "effective_char_count": self.effective_char_count,
            "word_count": self.word_count,
            "garbled_char_count": self.garbled_char_count,
            "garbled_ratio": self.garbled_ratio,
            "text_coverage": self.text_coverage,
            "image_coverage": self.image_coverage,
            "significant_image_count": self.significant_image_count,
            "significant_image_coverage": self.significant_image_coverage,
            "largest_image_area_ratio": self.largest_image_area_ratio,
            "requires_ocr": self.requires_ocr,
        }


class PageQualityDetector:
    def __init__(self, config: PDFParsingConfig) -> None:
        self.config = config

    def assess(
        self,
        *,
        text: str,
        page_width: float,
        page_height: float,
        text_bboxes: Sequence[BBoxTuple],
        image_bboxes: Sequence[BBoxTuple],
    ) -> PageQuality:
        visible_chars = [char for char in text if not char.isspace()]
        garbled_chars = [char for char in visible_chars if _is_garbled(char)]
        effective_char_count = len(visible_chars) - len(garbled_chars)
        garbled_ratio = len(garbled_chars) / len(visible_chars) if visible_chars else 0.0
        text_coverage = _coverage_ratio(text_bboxes, page_width, page_height)
        image_coverage = _coverage_ratio(image_bboxes, page_width, page_height)
        significant_images = _significant_image_rectangles(
            image_bboxes,
            page_width,
            page_height,
            min_area_ratio=self.config.significant_image_min_area_ratio,
            min_width_ratio=self.config.significant_image_min_width_ratio,
            min_height_ratio=self.config.significant_image_min_height_ratio,
        )
        significant_image_coverage = _coverage_ratio(
            significant_images,
            page_width,
            page_height,
        )
        largest_image_area_ratio = max(
            (
                _rectangle_area_ratio(rectangle, page_width, page_height)
                for rectangle in image_bboxes
            ),
            default=0.0,
        )

        page_type, requires_ocr = self._classify(
            effective_char_count=effective_char_count,
            garbled_ratio=garbled_ratio,
            image_coverage=image_coverage,
            has_significant_image=bool(significant_images),
        )
        confidence = _classification_confidence(
            page_type=page_type,
            effective_char_count=effective_char_count,
            min_effective_chars=self.config.min_effective_chars,
            garbled_ratio=garbled_ratio,
            image_coverage=image_coverage,
        )
        return PageQuality(
            page_type=page_type,
            confidence=confidence,
            requires_ocr=requires_ocr,
            effective_char_count=effective_char_count,
            word_count=len(re.findall(r"\w+", text, flags=re.UNICODE)),
            garbled_char_count=len(garbled_chars),
            garbled_ratio=round(garbled_ratio, 6),
            text_coverage=round(text_coverage, 6),
            image_coverage=round(image_coverage, 6),
            significant_image_count=len(significant_images),
            significant_image_coverage=round(significant_image_coverage, 6),
            largest_image_area_ratio=round(largest_image_area_ratio, 6),
        )

    def _classify(
        self,
        *,
        effective_char_count: int,
        garbled_ratio: float,
        image_coverage: float,
        has_significant_image: bool,
    ) -> tuple[PDFPageType, bool]:
        if effective_char_count == 0:
            if (
                image_coverage >= self.config.scanned_image_coverage_threshold
                or has_significant_image
            ):
                return PDFPageType.SCANNED, True
            return PDFPageType.EMPTY, False

        if garbled_ratio > self.config.max_garbled_ratio:
            return PDFPageType.SCANNED, True

        if (
            effective_char_count < self.config.min_effective_chars
            and (
                image_coverage >= self.config.scanned_image_coverage_threshold
                or has_significant_image
            )
        ):
            return PDFPageType.SCANNED, True

        if image_coverage >= self.config.mixed_image_coverage_threshold:
            # Mixed pages must enter the region router even when their native text is
            # readable: image/table areas still require independent extraction.
            return PDFPageType.MIXED, True

        return PDFPageType.TEXT, False


def _is_garbled(char: str) -> bool:
    return char == "\ufffd" or unicodedata.category(char) in {"Cc", "Cs"}


def _classification_confidence(
    *,
    page_type: PDFPageType,
    effective_char_count: int,
    min_effective_chars: int,
    garbled_ratio: float,
    image_coverage: float,
) -> float:
    if page_type is PDFPageType.EMPTY:
        return 1.0
    if page_type is PDFPageType.SCANNED:
        return round(max(0.5, image_coverage, garbled_ratio), 6)
    text_strength = min(1.0, effective_char_count / min_effective_chars)
    if page_type is PDFPageType.MIXED:
        return round(max(0.5, min(1.0, (text_strength + image_coverage) / 2)), 6)
    return round(max(0.5, (1.0 - garbled_ratio) * (0.8 + 0.2 * text_strength)), 6)


def _coverage_ratio(
    rectangles: Sequence[BBoxTuple],
    page_width: float,
    page_height: float,
) -> float:
    if page_width <= 0 or page_height <= 0:
        return 0.0
    clipped = []
    for x0, y0, x1, y1 in rectangles:
        bounded = (
            max(0.0, min(page_width, x0)),
            max(0.0, min(page_height, y0)),
            max(0.0, min(page_width, x1)),
            max(0.0, min(page_height, y1)),
        )
        if bounded[2] > bounded[0] and bounded[3] > bounded[1]:
            clipped.append(bounded)
    if not clipped:
        return 0.0

    x_coordinates = sorted({rect[0] for rect in clipped} | {rect[2] for rect in clipped})
    covered_area = 0.0
    for left, right in zip(x_coordinates, x_coordinates[1:], strict=False):
        if right <= left:
            continue
        y_intervals = sorted((y0, y1) for x0, y0, x1, y1 in clipped if x0 < right and x1 > left)
        merged_height = 0.0
        current_start: float | None = None
        current_end: float | None = None
        for start, end in y_intervals:
            if current_start is None or current_end is None:
                current_start, current_end = start, end
            elif start > current_end:
                merged_height += current_end - current_start
                current_start, current_end = start, end
            else:
                current_end = max(current_end, end)
        if current_start is not None and current_end is not None:
            merged_height += current_end - current_start
        covered_area += (right - left) * merged_height
    return min(1.0, covered_area / (page_width * page_height))


def _significant_image_rectangles(
    rectangles: Sequence[BBoxTuple],
    page_width: float,
    page_height: float,
    *,
    min_area_ratio: float,
    min_width_ratio: float,
    min_height_ratio: float,
) -> list[BBoxTuple]:
    if page_width <= 0 or page_height <= 0:
        return []
    significant: list[BBoxTuple] = []
    for rectangle in rectangles:
        x0, y0, x1, y1 = _clip_rectangle(rectangle, page_width, page_height)
        width_ratio = max(0.0, x1 - x0) / page_width
        height_ratio = max(0.0, y1 - y0) / page_height
        area_ratio = width_ratio * height_ratio
        if (
            area_ratio >= min_area_ratio
            and width_ratio >= min_width_ratio
            and height_ratio >= min_height_ratio
        ):
            significant.append((x0, y0, x1, y1))
    return significant


def _rectangle_area_ratio(
    rectangle: BBoxTuple,
    page_width: float,
    page_height: float,
) -> float:
    if page_width <= 0 or page_height <= 0:
        return 0.0
    x0, y0, x1, y1 = _clip_rectangle(rectangle, page_width, page_height)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) / (page_width * page_height)


def _clip_rectangle(
    rectangle: BBoxTuple,
    page_width: float,
    page_height: float,
) -> BBoxTuple:
    x0, y0, x1, y1 = rectangle
    return (
        max(0.0, min(page_width, x0)),
        max(0.0, min(page_height, y0)),
        max(0.0, min(page_width, x1)),
        max(0.0, min(page_height, y1)),
    )
