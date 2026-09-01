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


def extract_native_tables(page: pymupdf.Page) -> NativeTableExtraction:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            finder: Any = page.find_tables()  # type: ignore[no-untyped-call]
    except Exception:
        return NativeTableExtraction(tables=(), failed=True)

    regions: list[NativeTableRegion] = []
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
        regions.append(
            NativeTableRegion(
                bbox=bbox,
                markdown=_to_markdown(padded),
                metadata={
                    "table_detector": "pymupdf",
                    "native_table_number": table_number,
                    "row_count": len(padded),
                    "column_count": column_count,
                },
            )
        )
    return NativeTableExtraction(tables=tuple(regions))


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).replace("|", "\\|")


def _to_markdown(rows: list[list[str]]) -> str:
    header = rows[0]
    lines = [f"| {' | '.join(header)} |", f"| {' | '.join('---' for _ in header)} |"]
    lines.extend(f"| {' | '.join(row)} |" for row in rows[1:])
    return "\n".join(lines)
