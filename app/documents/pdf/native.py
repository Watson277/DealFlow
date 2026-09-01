"""Native PyMuPDF extraction into the shared PDF page IR."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

import pymupdf
from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import PDFPreflightCode, PDFPreflightError
from app.documents.pdf.models import (
    BlockIR,
    BoundingBox,
    PageIR,
    ParseWarning,
    PDFBlockSource,
    PDFBlockType,
    PDFDocumentType,
    PDFPageType,
    PDFWarningSeverity,
)
from app.documents.pdf.preflight import PDFPreflightResult, PDFPreflightValidator
from app.documents.pdf.quality import BBoxTuple, PageQuality, PageQualityDetector


@dataclass(frozen=True, slots=True)
class NativePDFDocument:
    text: str
    page_count: int
    document_type: PDFDocumentType
    pages: tuple[PageIR, ...]
    warnings: tuple[ParseWarning, ...]
    preflight: PDFPreflightResult
    parser_version: str


@dataclass(frozen=True, slots=True)
class _BlockCandidate:
    bbox: BoundingBox
    type: PDFBlockType
    text: str | None
    raw_text: str | None
    metadata: dict[str, JsonValue]


class NativePDFParser:
    def __init__(self, config: PDFParsingConfig | None = None) -> None:
        self.config = config or PDFParsingConfig()
        self.preflight = PDFPreflightValidator(self.config)
        self.quality = PageQualityDetector(self.config)

    def parse(self, content: bytes, filename: str) -> NativePDFDocument:
        try:
            document = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
        except Exception as exc:
            raise PDFPreflightError(
                PDFPreflightCode.INVALID, "PDF document is damaged or unreadable"
            ) from exc

        with document:
            result = self.preflight.validate(
                document,
                filename=filename,
                file_size_bytes=len(content),
            )
            pages = tuple(
                self._extract_page(_load_page(document, index), index + 1)
                for index in range(document.page_count)
            )

        warnings = tuple(warning for page in pages for warning in page.warnings)
        return NativePDFDocument(
            text=_plain_text(pages),
            page_count=result.page_count,
            document_type=_document_type(pages),
            pages=pages,
            warnings=warnings,
            preflight=result,
            parser_version=self.config.parser_version,
        )

    def _extract_page(self, page: pymupdf.Page, page_number: int) -> PageIR:
        width = float(page.rect.width)
        height = float(page.rect.height)
        flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        layout: dict[str, Any] = page.get_text("dict", sort=True, flags=flags)  # type: ignore[no-untyped-call]

        candidates = self._text_candidates(layout.get("blocks", []), width, height)
        image_candidates = self._image_candidates(page, width, height)
        candidates.extend(image_candidates)
        candidates.sort(key=lambda candidate: (candidate.bbox.y0, candidate.bbox.x0))

        blocks = tuple(
            BlockIR(
                block_id=f"p{page_number}_b{index:04d}",
                type=candidate.type,
                bbox=candidate.bbox,
                source=PDFBlockSource.NATIVE,
                reading_order=index - 1,
                text=candidate.text,
                raw_text=candidate.raw_text,
                metadata=candidate.metadata,
            )
            for index, candidate in enumerate(candidates, start=1)
        )
        text_candidates = [candidate for candidate in candidates if candidate.text]
        quality = self.quality.assess(
            text="\n".join(candidate.text or "" for candidate in text_candidates),
            page_width=width,
            page_height=height,
            text_bboxes=[_bbox_tuple(candidate.bbox) for candidate in text_candidates],
            image_bboxes=[_bbox_tuple(candidate.bbox) for candidate in image_candidates],
        )
        return PageIR(
            page_number=page_number,
            width=width,
            height=height,
            page_type=quality.page_type,
            confidence=quality.confidence,
            blocks=blocks,
            warnings=_quality_warnings(page_number, quality),
            metadata={"quality": quality.as_metadata()},
        )

    @staticmethod
    def _text_candidates(
        raw_blocks: list[dict[str, Any]],
        width: float,
        height: float,
    ) -> list[_BlockCandidate]:
        candidates: list[_BlockCandidate] = []
        for raw_block in raw_blocks:
            if raw_block.get("type") != 0:
                continue
            bbox = _bounded_bbox(raw_block.get("bbox"), width, height)
            if bbox is None:
                continue
            lines: list[str] = []
            font_names: set[str] = set()
            font_sizes: set[float] = set()
            span_count = 0
            for line in raw_block.get("lines", []):
                spans = line.get("spans", [])
                line_text = "".join(str(span.get("text", "")) for span in spans)
                if line_text.strip():
                    lines.append(line_text.rstrip())
                for span in spans:
                    span_count += 1
                    if span.get("font"):
                        font_names.add(str(span["font"]))
                    try:
                        font_sizes.add(round(float(span.get("size", 0.0)), 3))
                    except (TypeError, ValueError):
                        continue
            text = "\n".join(lines).strip()
            if not text:
                continue
            candidates.append(
                _BlockCandidate(
                    bbox=bbox,
                    type=PDFBlockType.TEXT,
                    text=text,
                    raw_text=text,
                    metadata={
                        "native_block_number": int(raw_block.get("number", len(candidates))),
                        "span_count": span_count,
                        "font_names": cast(JsonValue, sorted(font_names)),
                        "font_sizes": cast(
                            JsonValue, sorted(size for size in font_sizes if size > 0)
                        ),
                    },
                )
            )
        return candidates

    @staticmethod
    def _image_candidates(
        page: pymupdf.Page,
        width: float,
        height: float,
    ) -> list[_BlockCandidate]:
        candidates: list[_BlockCandidate] = []
        image_info: list[dict[str, Any]] = page.get_image_info()
        for image in image_info:
            bbox = _bounded_bbox(image.get("bbox"), width, height)
            if bbox is None:
                continue
            metadata: dict[str, JsonValue] = {}
            for key in ("width", "height", "xres", "yres", "bpc", "size", "cs-name"):
                value = image.get(key)
                if value is None or isinstance(value, (str, int, float, bool)):
                    metadata[key] = value
            candidates.append(
                _BlockCandidate(
                    bbox=bbox,
                    type=PDFBlockType.IMAGE,
                    text=None,
                    raw_text=None,
                    metadata=metadata,
                )
            )
        return candidates


def _bounded_bbox(value: object, width: float, height: float) -> BoundingBox | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        coordinates = tuple(float(item) for item in value[:4])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in coordinates):
        return None
    x0, y0, x1, y1 = coordinates
    x0, x1 = sorted((max(0.0, min(width, x0)), max(0.0, min(width, x1))))
    y0, y1 = sorted((max(0.0, min(height, y0)), max(0.0, min(height, y1))))
    if x1 <= x0 or y1 <= y0:
        return None
    return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _load_page(document: pymupdf.Document, index: int) -> pymupdf.Page:
    return cast(pymupdf.Page, document.load_page(index))  # type: ignore[no-untyped-call]


def _bbox_tuple(bbox: BoundingBox) -> BBoxTuple:
    return (bbox.x0, bbox.y0, bbox.x1, bbox.y1)


def _quality_warnings(page_number: int, quality: PageQuality) -> tuple[ParseWarning, ...]:
    warnings: list[ParseWarning] = []
    if quality.page_type is PDFPageType.EMPTY:
        warnings.append(
            ParseWarning(
                code="EMPTY_PAGE",
                message="Page contains no native text or substantial image content",
                severity=PDFWarningSeverity.INFO,
                page_number=page_number,
            )
        )
    elif quality.requires_ocr:
        warnings.append(
            ParseWarning(
                code="OCR_REQUIRED",
                message="Native page content is insufficient and requires OCR fallback",
                page_number=page_number,
                details=quality.as_metadata(),
            )
        )
    if quality.garbled_ratio > 0:
        warnings.append(
            ParseWarning(
                code="NATIVE_TEXT_GARBLED",
                message="Native text contains invalid or replacement characters",
                page_number=page_number,
                details={"garbled_ratio": quality.garbled_ratio},
            )
        )
    return tuple(warnings)


def _plain_text(pages: tuple[PageIR, ...]) -> str:
    sections: list[str] = []
    for page in pages:
        text = "\n\n".join(block.text for block in page.blocks if block.text)
        if text:
            sections.append(f"--- Page {page.page_number} ---\n{text}")
    return "\n\n".join(sections)


def _document_type(pages: tuple[PageIR, ...]) -> PDFDocumentType:
    page_types = {page.page_type for page in pages if page.page_type is not PDFPageType.EMPTY}
    if not page_types or page_types == {PDFPageType.TEXT}:
        return PDFDocumentType.TEXT_BASED
    if page_types == {PDFPageType.SCANNED}:
        return PDFDocumentType.SCANNED
    return PDFDocumentType.MIXED
