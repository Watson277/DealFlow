"""Scanned-table structure recognition followed by cell-level OCR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import cv2
import numpy as np
import numpy.typing as npt
import pymupdf
from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import PDFTableRecognitionError
from app.documents.pdf.models import BoundingBox
from app.documents.pdf.ocr import OCRProvider

GrayImage = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class ScannedTableResult:
    bbox: BoundingBox
    markdown: str
    provider: str
    row_count: int
    column_count: int
    metadata: dict[str, JsonValue]


class TableStructureRecognizer(Protocol):
    @property
    def name(self) -> str: ...

    def recognize(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> ScannedTableResult: ...


class OpenCVTableStructureRecognizer:
    """Recover ruled table grids and OCR each detected cell independently."""

    name = "opencv-grid-tsr"

    def __init__(self, config: PDFParsingConfig, ocr_provider: OCRProvider) -> None:
        self.config = config
        self.ocr_provider = ocr_provider

    def recognize(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> ScannedTableResult:
        clip = pymupdf.Rect(  # type: ignore[no-untyped-call]
            bbox.x0, bbox.y0, bbox.x1, bbox.y1
        )
        pixmap = page.get_pixmap(
            dpi=self.config.layout_detection_dpi,
            colorspace=pymupdf.csRGB,
            alpha=False,
            clip=clip,
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
        horizontal = cast(
            GrayImage,
            cv2.morphologyEx(
                binary,
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    (max(15, pixmap.width // 12), 1),
                ),
            ),
        )
        vertical = cast(
            GrayImage,
            cv2.morphologyEx(
                binary,
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    (1, max(15, pixmap.height // 12)),
                ),
            ),
        )
        x_lines = _line_positions(vertical, axis=0)
        y_lines = _line_positions(horizontal, axis=1)
        if len(x_lines) < 2 or len(y_lines) < 2:
            raise PDFTableRecognitionError("table grid does not contain enough row/column lines")

        row_count = len(y_lines) - 1
        column_count = len(x_lines) - 1
        if row_count * column_count > self.config.tsr_max_cells:
            raise PDFTableRecognitionError(
                f"table grid exceeds the configured {self.config.tsr_max_cells}-cell limit"
            )

        rows: list[list[str]] = []
        cells_metadata: list[JsonValue] = []
        for row_index, (top, bottom) in enumerate(zip(y_lines, y_lines[1:], strict=False)):
            row: list[str] = []
            for column_index, (left, right) in enumerate(zip(x_lines, x_lines[1:], strict=False)):
                if right - left < 3 or bottom - top < 3:
                    row.append("")
                    continue
                cell_bbox = _pixel_to_page_bbox(
                    left + 1,
                    top + 1,
                    right - 1,
                    bottom - 1,
                    table_bbox=bbox,
                    image_width=pixmap.width,
                    image_height=pixmap.height,
                )
                result = self.ocr_provider.recognize_region(page, page_number, cell_bbox)
                text = " ".join(block.text for block in result.blocks).strip()
                row.append(_escape_cell(text))
                cells_metadata.append(
                    {
                        "row": row_index,
                        "column": column_index,
                        "bbox": cell_bbox.model_dump(mode="json"),
                        "text": text,
                    }
                )
            rows.append(row)
        if not any(cell for row in rows for cell in row):
            raise PDFTableRecognitionError("cell OCR returned no table content")

        return ScannedTableResult(
            bbox=bbox,
            markdown=_to_markdown(rows),
            provider=self.name,
            row_count=row_count,
            column_count=column_count,
            metadata={
                "table_detector": self.name,
                "ocr_provider": self.ocr_provider.name,
                "row_count": row_count,
                "column_count": column_count,
                "cells": cells_metadata,
            },
        )


def _line_positions(mask: GrayImage, *, axis: int) -> list[int]:
    projection = np.count_nonzero(mask, axis=axis)
    orthogonal_length = mask.shape[axis]
    indices = np.flatnonzero(projection >= max(3, orthogonal_length * 0.35)).tolist()
    if not indices:
        return []
    clusters: list[list[int]] = [[int(indices[0])]]
    for index in indices[1:]:
        if int(index) - clusters[-1][-1] <= 3:
            clusters[-1].append(int(index))
        else:
            clusters.append([int(index)])
    return [round(sum(cluster) / len(cluster)) for cluster in clusters]


def _pixel_to_page_bbox(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    table_bbox: BoundingBox,
    image_width: int,
    image_height: int,
) -> BoundingBox:
    table_width = table_bbox.x1 - table_bbox.x0
    table_height = table_bbox.y1 - table_bbox.y0
    return BoundingBox(
        x0=table_bbox.x0 + x0 * table_width / image_width,
        y0=table_bbox.y0 + y0 * table_height / image_height,
        x1=table_bbox.x0 + x1 * table_width / image_width,
        y1=table_bbox.y0 + y1 * table_height / image_height,
    )


def _escape_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def _to_markdown(rows: list[list[str]]) -> str:
    column_count = max((len(row) for row in rows), default=0)
    if column_count == 0:
        raise PDFTableRecognitionError("table contains no columns")
    padded = [row + [""] * (column_count - len(row)) for row in rows]
    header = padded[0]
    lines = [f"| {' | '.join(header)} |", f"| {' | '.join('---' for _ in header)} |"]
    lines.extend(f"| {' | '.join(row)} |" for row in padded[1:])
    return "\n".join(lines)
