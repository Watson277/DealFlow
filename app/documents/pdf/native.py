"""Native PyMuPDF extraction into the shared PDF page IR."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

import pymupdf
from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import PDFOCRError, PDFPreflightCode, PDFPreflightError
from app.documents.pdf.layout import PDFLayoutAnalyzer
from app.documents.pdf.layout.tables import NativeTableExtraction, extract_native_tables
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
from app.documents.pdf.ocr import OCRPageResult, OCRProvider, TesseractOCRProvider
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
    source: PDFBlockSource
    confidence: float | None
    table_markdown: str | None
    metadata: dict[str, JsonValue]


class NativePDFParser:
    def __init__(
        self,
        config: PDFParsingConfig | None = None,
        ocr_provider: OCRProvider | None = None,
    ) -> None:
        self.config = config or PDFParsingConfig()
        self.preflight = PDFPreflightValidator(self.config)
        self.quality = PageQualityDetector(self.config)
        self.layout = PDFLayoutAnalyzer(self.config)
        self.ocr_provider = (
            ocr_provider if ocr_provider is not None else TesseractOCRProvider(self.config)
        )

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
            extracted_pages = tuple(
                self._extract_page(_load_page(document, index), index + 1)
                for index in range(document.page_count)
            )
            pages = self.layout.analyze(extracted_pages)

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

        native_text_candidates = self._text_candidates(layout.get("blocks", []), width, height)
        image_candidates = self._image_candidates(page, width, height)
        table_extraction = (
            extract_native_tables(page)
            if self.config.layout_enabled and self.config.layout_detect_tables
            else NativeTableExtraction(tables=())
        )
        table_candidates = _table_candidates(table_extraction)
        quality = self.quality.assess(
            text="\n".join(candidate.text or "" for candidate in native_text_candidates),
            page_width=width,
            page_height=height,
            text_bboxes=[_bbox_tuple(candidate.bbox) for candidate in native_text_candidates],
            image_bboxes=[_bbox_tuple(candidate.bbox) for candidate in image_candidates],
        )

        candidates = [*native_text_candidates, *image_candidates, *table_candidates]
        warnings = list(
            _quality_warnings(
                page_number,
                quality,
                include_ocr_required=not self.config.ocr_enabled,
            )
        )
        ocr_metadata: dict[str, JsonValue] = {
            "requested": quality.requires_ocr,
            "enabled": self.config.ocr_enabled,
            "applied": False,
        }
        if table_extraction.failed:
            warnings.append(
                ParseWarning(
                    code="TABLE_DETECTION_FAILED",
                    message="Native table detection failed; positioned text was retained",
                    page_number=page_number,
                )
            )
        if quality.requires_ocr and self.config.ocr_enabled:
            try:
                ocr_result = self.ocr_provider.recognize_page(page, page_number)
            except PDFOCRError as exc:
                warnings.append(
                    ParseWarning(
                        code="OCR_FAILED",
                        message="OCR fallback could not process this page",
                        page_number=page_number,
                        details={
                            "error_code": exc.code.value,
                            "provider": self.ocr_provider.name,
                        },
                    )
                )
                ocr_metadata.update(
                    {
                        "provider": self.ocr_provider.name,
                        "error_code": exc.code.value,
                    }
                )
            else:
                ocr_metadata.update(_ocr_metadata(ocr_result))
                if ocr_result.blocks:
                    candidates = [
                        *_ocr_candidates(ocr_result),
                        *image_candidates,
                        *table_candidates,
                    ]
                    ocr_metadata["applied"] = True
                    ocr_metadata["native_text_blocks_replaced"] = len(native_text_candidates)
                    warnings.append(
                        ParseWarning(
                            code="OCR_APPLIED",
                            message="OCR fallback supplied positioned text for this page",
                            severity=PDFWarningSeverity.INFO,
                            page_number=page_number,
                            details={
                                "provider": ocr_result.provider,
                                "block_count": len(ocr_result.blocks),
                            },
                        )
                    )
                else:
                    warnings.append(
                        ParseWarning(
                            code="OCR_EMPTY_RESULT",
                            message="OCR completed but found no text on this page",
                            page_number=page_number,
                            details={"provider": ocr_result.provider},
                        )
                    )

        candidates.sort(key=lambda candidate: (candidate.bbox.y0, candidate.bbox.x0))

        blocks = tuple(
            BlockIR(
                block_id=f"p{page_number}_b{index:04d}",
                type=candidate.type,
                bbox=candidate.bbox,
                source=candidate.source,
                reading_order=index - 1,
                text=candidate.text,
                raw_text=candidate.raw_text,
                confidence=candidate.confidence,
                table_markdown=candidate.table_markdown,
                metadata=candidate.metadata,
            )
            for index, candidate in enumerate(candidates, start=1)
        )
        return PageIR(
            page_number=page_number,
            width=width,
            height=height,
            page_type=quality.page_type,
            confidence=quality.confidence,
            blocks=blocks,
            warnings=tuple(warnings),
            metadata={
                "quality": quality.as_metadata(),
                "ocr": ocr_metadata,
                "table_detection": {
                    "enabled": self.config.layout_enabled and self.config.layout_detect_tables,
                    "table_count": len(table_extraction.tables),
                    "failed": table_extraction.failed,
                },
            },
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
                    source=PDFBlockSource.NATIVE,
                    confidence=None,
                    table_markdown=None,
                    metadata={
                        "native_block_number": int(raw_block.get("number", len(candidates))),
                        "span_count": span_count,
                        "font_names": cast(JsonValue, sorted(font_names)),
                        "font_sizes": cast(
                            JsonValue, sorted(size for size in font_sizes if size > 0)
                        ),
                        "is_bold": any("bold" in name.casefold() for name in font_names),
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
                    source=PDFBlockSource.NATIVE,
                    confidence=None,
                    table_markdown=None,
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


def _quality_warnings(
    page_number: int,
    quality: PageQuality,
    *,
    include_ocr_required: bool,
) -> tuple[ParseWarning, ...]:
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
    elif quality.requires_ocr and include_ocr_required:
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


def _ocr_candidates(result: OCRPageResult) -> list[_BlockCandidate]:
    return [
        _BlockCandidate(
            bbox=block.bbox,
            type=PDFBlockType.TEXT,
            text=block.text,
            raw_text=block.text,
            source=PDFBlockSource.OCR,
            confidence=block.confidence,
            table_markdown=None,
            metadata=block.metadata,
        )
        for block in result.blocks
    ]


def _ocr_metadata(result: OCRPageResult) -> dict[str, JsonValue]:
    return {
        "provider": result.provider,
        "languages": result.languages,
        "dpi": result.dpi,
        "rendered_width": result.rendered_width,
        "rendered_height": result.rendered_height,
        "block_count": len(result.blocks),
    }


def _table_candidates(extraction: NativeTableExtraction) -> list[_BlockCandidate]:
    return [
        _BlockCandidate(
            bbox=table.bbox,
            type=PDFBlockType.TABLE,
            text=None,
            raw_text=None,
            source=PDFBlockSource.DERIVED,
            confidence=None,
            table_markdown=table.markdown,
            metadata=table.metadata,
        )
        for table in extraction.tables
    ]


def _plain_text(pages: tuple[PageIR, ...]) -> str:
    sections: list[str] = []
    for page in pages:
        content: list[str] = []
        for block in page.blocks:
            if block.type in {PDFBlockType.HEADER, PDFBlockType.FOOTER}:
                continue
            if block.table_markdown:
                content.append(block.table_markdown)
            elif block.text:
                content.append(block.text)
        text = "\n\n".join(content)
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
