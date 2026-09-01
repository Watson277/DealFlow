"""Page-image layout detection used before OCR on scanned and mixed pages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast

import cv2
import numpy as np
import numpy.typing as npt
import pymupdf
from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.models import BoundingBox

PixelBox = tuple[int, int, int, int]
GrayImage = npt.NDArray[np.uint8]


class LayoutRegionType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


@dataclass(frozen=True, slots=True)
class LayoutRegion:
    region_id: str
    type: LayoutRegionType
    bbox: BoundingBox
    confidence: float
    metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LayoutDetectionResult:
    regions: tuple[LayoutRegion, ...]
    provider: str
    rendered_width: int
    rendered_height: int
    dpi: int
    fallback_used: bool = False


class LayoutDetector(Protocol):
    @property
    def name(self) -> str: ...

    def detect(self, page: pymupdf.Page, page_number: int) -> LayoutDetectionResult: ...


class OpenCVLayoutDetector:
    """Deterministic region detector with table-line and connected-component routing."""

    name = "opencv-heuristic-layout"

    def __init__(self, config: PDFParsingConfig) -> None:
        self.config = config

    def detect(self, page: pymupdf.Page, page_number: int) -> LayoutDetectionResult:
        pixmap = page.get_pixmap(
            dpi=self.config.layout_detection_dpi,
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height,
            pixmap.width,
            pixmap.n,
        )
        gray = cast(GrayImage, cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
        binary = cast(
            GrayImage,
            cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
            )[1],
        )

        table_boxes = _table_boxes(binary, self.config.layout_min_region_area_ratio)
        text_boxes = _text_boxes(
            binary,
            table_boxes,
            self.config.layout_min_region_area_ratio,
        )
        image_boxes = _image_boxes(
            gray,
            table_boxes,
            text_boxes,
            self.config.layout_min_region_area_ratio,
        )
        typed_boxes = [
            *((LayoutRegionType.TEXT, box, 0.72) for box in text_boxes),
            *((LayoutRegionType.TABLE, box, 0.86) for box in table_boxes),
            *((LayoutRegionType.IMAGE, box, 0.62) for box in image_boxes),
        ]
        fallback_used = not typed_boxes
        if fallback_used:
            typed_boxes = [
                (
                    LayoutRegionType.TEXT,
                    (0, 0, pixmap.width, pixmap.height),
                    0.25,
                )
            ]

        typed_boxes.sort(key=lambda item: (item[1][1], item[1][0], item[0].value))
        regions = tuple(
            LayoutRegion(
                region_id=f"p{page_number}_r{index:04d}",
                type=region_type,
                bbox=_to_pdf_bbox(
                    box,
                    page_width=float(page.rect.width),
                    page_height=float(page.rect.height),
                    image_width=pixmap.width,
                    image_height=pixmap.height,
                ),
                confidence=confidence,
                metadata={
                    "layout_provider": self.name,
                    "pixel_bbox": list(box),
                },
            )
            for index, (region_type, box, confidence) in enumerate(typed_boxes, start=1)
        )
        return LayoutDetectionResult(
            regions=regions,
            provider=self.name,
            rendered_width=pixmap.width,
            rendered_height=pixmap.height,
            dpi=self.config.layout_detection_dpi,
            fallback_used=fallback_used,
        )


def _table_boxes(binary: GrayImage, min_area_ratio: float) -> list[PixelBox]:
    height, width = binary.shape
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(20, width // 24), 1),
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(20, height // 32)),
    )
    horizontal = cast(GrayImage, cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel))
    vertical = cast(GrayImage, cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel))
    grid = cast(GrayImage, cv2.bitwise_or(horizontal, vertical))
    grid = cast(
        GrayImage,
        cv2.dilate(grid, np.ones((5, 5), dtype=np.uint8), iterations=2),
    )
    minimum_area = width * height * max(min_area_ratio, 0.003)
    boxes: list[PixelBox] = []
    for contour in _external_contours(grid):
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if box_width * box_height < minimum_area:
            continue
        if box_width < width * 0.12 or box_height < height * 0.04:
            continue
        horizontal_pixels = int(np.count_nonzero(horizontal[y : y + box_height, x : x + box_width]))
        vertical_pixels = int(np.count_nonzero(vertical[y : y + box_height, x : x + box_width]))
        if horizontal_pixels < box_width or vertical_pixels < box_height:
            continue
        boxes.append(_pad_box((x, y, x + box_width, y + box_height), width, height, 3))
    return _deduplicate_boxes(boxes, overlap_threshold=0.75)


def _text_boxes(
    binary: GrayImage,
    table_boxes: list[PixelBox],
    min_area_ratio: float,
) -> list[PixelBox]:
    height, width = binary.shape
    working = binary.copy()
    for x0, y0, x1, y1 in table_boxes:
        working[y0:y1, x0:x1] = 0
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(7, width // 90), max(3, height // 300)),
    )
    grouped = cast(GrayImage, cv2.dilate(working, kernel, iterations=2))
    minimum_area = width * height * min_area_ratio
    boxes: list[PixelBox] = []
    for contour in _external_contours(grouped):
        x, y, box_width, box_height = cv2.boundingRect(contour)
        area = box_width * box_height
        if area < minimum_area or box_width < width * 0.025 or box_height < 4:
            continue
        ink_ratio = float(np.count_nonzero(working[y : y + box_height, x : x + box_width])) / area
        if not 0.01 <= ink_ratio <= 0.75:
            continue
        boxes.append(_pad_box((x, y, x + box_width, y + box_height), width, height, 4))
    return _merge_nearby_text_boxes(boxes, width, height)


def _image_boxes(
    gray: GrayImage,
    table_boxes: list[PixelBox],
    text_boxes: list[PixelBox],
    min_area_ratio: float,
) -> list[PixelBox]:
    height, width = gray.shape
    edges = cv2.Canny(gray, 80, 180)
    closed = cast(
        GrayImage,
        cv2.morphologyEx(
            edges,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)),
            iterations=2,
        ),
    )
    minimum_area = width * height * max(min_area_ratio * 8, 0.015)
    boxes: list[PixelBox] = []
    excluded = [*table_boxes, *text_boxes]
    for contour in _external_contours(closed):
        x, y, box_width, box_height = cv2.boundingRect(contour)
        box = (x, y, x + box_width, y + box_height)
        area = box_width * box_height
        if area < minimum_area or box_width < width * 0.08 or box_height < height * 0.05:
            continue
        if box_width >= width * 0.95 and box_height >= height * 0.95:
            continue
        if any(_smaller_box_overlap_pixels(box, other) >= 0.70 for other in excluded):
            continue
        pixel_std = float(np.std(gray[y : y + box_height, x : x + box_width]))
        if pixel_std < 18.0:
            continue
        boxes.append(_pad_box(box, width, height, 4))
    return _deduplicate_boxes(boxes, overlap_threshold=0.70)


def _external_contours(image: GrayImage) -> tuple[Any, ...]:
    contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return tuple(contours)


def _merge_nearby_text_boxes(
    boxes: list[PixelBox],
    page_width: int,
    page_height: int,
) -> list[PixelBox]:
    pending = sorted(boxes, key=lambda box: (box[1], box[0]))
    merged: list[PixelBox] = []
    for box in pending:
        for index, existing in enumerate(merged):
            vertical_gap = max(0, box[1] - existing[3], existing[1] - box[3])
            horizontal_overlap = max(0, min(box[2], existing[2]) - max(box[0], existing[0]))
            smaller_width = min(box[2] - box[0], existing[2] - existing[0])
            if (
                vertical_gap <= page_height * 0.012
                and smaller_width > 0
                and horizontal_overlap / smaller_width >= 0.45
            ):
                merged[index] = _union_pixel_boxes(existing, box)
                break
        else:
            merged.append(box)
    return [
        _pad_box(box, page_width, page_height, 2)
        for box in _deduplicate_boxes(merged, overlap_threshold=0.80)
    ]


def _deduplicate_boxes(boxes: list[PixelBox], overlap_threshold: float) -> list[PixelBox]:
    retained: list[PixelBox] = []
    for box in sorted(boxes, key=_pixel_area, reverse=True):
        if any(_smaller_box_overlap_pixels(box, other) >= overlap_threshold for other in retained):
            continue
        retained.append(box)
    return sorted(retained, key=lambda box: (box[1], box[0]))


def _to_pdf_bbox(
    box: PixelBox,
    *,
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
) -> BoundingBox:
    x0, y0, x1, y1 = box
    return BoundingBox(
        x0=max(0.0, min(page_width, x0 * page_width / image_width)),
        y0=max(0.0, min(page_height, y0 * page_height / image_height)),
        x1=max(0.0, min(page_width, x1 * page_width / image_width)),
        y1=max(0.0, min(page_height, y1 * page_height / image_height)),
    )


def _pad_box(box: PixelBox, width: int, height: int, padding: int) -> PixelBox:
    return (
        max(0, box[0] - padding),
        max(0, box[1] - padding),
        min(width, box[2] + padding),
        min(height, box[3] + padding),
    )


def _union_pixel_boxes(first: PixelBox, second: PixelBox) -> PixelBox:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def _pixel_area(box: PixelBox) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _smaller_box_overlap_pixels(first: PixelBox, second: PixelBox) -> float:
    overlap_width = max(0, min(first[2], second[2]) - max(first[0], second[0]))
    overlap_height = max(0, min(first[3], second[3]) - max(first[1], second[1]))
    smaller_area = min(_pixel_area(first), _pixel_area(second))
    return overlap_width * overlap_height / smaller_area if smaller_area else 0.0
