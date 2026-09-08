"""Native table recovery using PyMuPDF's positioned cell extraction."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import Any

import pymupdf
from pydantic import JsonValue

from app.documents.pdf.models import BoundingBox


@dataclass(frozen=True, slots=True)
class NativeTableRegion:
    bbox: BoundingBox
    markdown: str
    metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class NativeTableExtraction:
    tables: tuple[NativeTableRegion, ...]
    failed: bool = False
    rejected_count: int = 0
    rejection_reasons: tuple[str, ...] = ()


def extract_native_tables(page: pymupdf.Page) -> NativeTableExtraction:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            finder: Any = page.find_tables()  # type: ignore[no-untyped-call]
    except Exception:
        return NativeTableExtraction(tables=(), failed=True)

    regions: list[NativeTableRegion] = []
    rejection_reasons: list[str] = []
    for table_number, table in enumerate(finder.tables, start=1):
        rows = table.extract()
        normalized = [[_cell_text(cell) for cell in row] for row in rows]
        if len(normalized) < 2 or max((len(row) for row in normalized), default=0) < 2:
            continue
        non_empty = sum(bool(cell) for row in normalized for cell in row)
        if non_empty < 2:
            continue
        try:
            bbox = BoundingBox(
                x0=float(table.bbox[0]),
                y0=float(table.bbox[1]),
                x1=float(table.bbox[2]),
                y1=float(table.bbox[3]),
            )
        except (IndexError, TypeError, ValueError):
            continue
        column_count = max(len(row) for row in normalized)
        padded = [row + [""] * (column_count - len(row)) for row in normalized]
        accepted, reason, quality = _table_quality(
            padded,
            bbox,
            page_width=float(page.rect.width),
            page_height=float(page.rect.height),
        )
        if not accepted:
            rejection_reasons.append(reason)
            continue
        regions.append(
            NativeTableRegion(
                bbox=bbox,
                markdown=_to_markdown(padded),
                metadata={
                    "table_detector": "pymupdf",
                    "native_table_number": table_number,
                    "row_count": len(padded),
                    "column_count": column_count,
                    "quality_gate_passed": True,
                    **quality,
                },
            )
        )
    return NativeTableExtraction(
        tables=tuple(regions),
        rejected_count=len(rejection_reasons),
        rejection_reasons=tuple(rejection_reasons),
    )


def _table_quality(
    rows: list[list[str]],
    bbox: BoundingBox,
    *,
    page_width: float,
    page_height: float,
) -> tuple[bool, str, dict[str, JsonValue]]:
    """Reject line-art and chart grids before they can erase native body text."""

    row_count = len(rows)
    column_count = max((len(row) for row in rows), default=0)
    total_cells = row_count * column_count
    non_empty = sum(bool(cell) for row in rows for cell in row)
    density = non_empty / total_cells if total_cells else 0.0
    populated_rows = sum(any(row) for row in rows)
    populated_columns = sum(
        any(rows[row_index][column_index] for row_index in range(row_count))
        for column_index in range(column_count)
    )
    page_area = page_width * page_height
    area_ratio = (
        ((bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0)) / page_area if page_area > 0 else 0.0
    )
    metadata: dict[str, JsonValue] = {
        "non_empty_cell_count": non_empty,
        "cell_density": round(density, 6),
        "populated_row_ratio": round(populated_rows / row_count, 6) if row_count else 0.0,
        "populated_column_ratio": (
            round(populated_columns / column_count, 6) if column_count else 0.0
        ),
        "page_area_ratio": round(area_ratio, 6),
    }
    if density < 0.20:
        return False, "sparse_cells", metadata
    if non_empty < max(4, row_count + column_count):
        return False, "insufficient_structural_content", metadata
    if area_ratio > 0.85:
        return False, "implausible_page_coverage", metadata
    return True, "accepted", metadata


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).replace("|", "\\|")


def _to_markdown(rows: list[list[str]]) -> str:
    header = rows[0]
    lines = [f"| {' | '.join(header)} |", f"| {' | '.join('---' for _ in header)} |"]
    lines.extend(f"| {' | '.join(row)} |" for row in rows[1:])
    return "\n".join(lines)
