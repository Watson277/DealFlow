"""Native PyMuPDF extraction into the shared PDF page IR."""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import pymupdf
from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import (
    PDFOCRError,
    PDFPreflightCode,
    PDFPreflightError,
    PDFTableRecognitionError,
    PDFVisionError,
)
from app.documents.pdf.fusion import BlockFusion
from app.documents.pdf.layout.analyzer import PDFLayoutAnalyzer
from app.documents.pdf.layout.detection import (
    LayoutDetectionResult,
    LayoutDetector,
    LayoutRegion,
    LayoutRegionType,
    OpenCVLayoutDetector,
)
from app.documents.pdf.layout.tables import NativeTableExtraction, extract_native_tables
from app.documents.pdf.layout.tsr import (
    OpenCVTableStructureRecognizer,
    ScannedTableResult,
    TableStructureRecognizer,
)
from app.documents.pdf.models import (
    BlockIR,
    BoundingBox,
    DocumentIR,
    PageIR,
    ParseWarning,
    PDFBlockSource,
    PDFBlockType,
    PDFDocumentType,
    PDFPageType,
    PDFParseStatus,
    PDFWarningSeverity,
)
from app.documents.pdf.ocr import OCRPageResult, OCRProvider, TesseractOCRProvider
from app.documents.pdf.preflight import PDFPreflightResult, PDFPreflightValidator
from app.documents.pdf.quality import BBoxTuple, PageQuality, PageQualityDetector
from app.documents.pdf.vision import DisabledVisionProvider, VisionProvider, VisionRegionResult


@dataclass(frozen=True, slots=True)
class NativePDFDocument:
    text: str
    page_count: int
    document_type: PDFDocumentType
    pages: tuple[PageIR, ...]
    warnings: tuple[ParseWarning, ...]
    preflight: PDFPreflightResult
    parser_version: str
    ir: DocumentIR


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


@dataclass(frozen=True, slots=True)
class _RoutedExtraction:
    candidates: list[_BlockCandidate]
    warnings: list[ParseWarning]
    metadata: dict[str, JsonValue]


class NativePDFParser:
    def __init__(
        self,
        config: PDFParsingConfig | None = None,
        ocr_provider: OCRProvider | None = None,
        layout_detector: LayoutDetector | None = None,
        table_recognizer: TableStructureRecognizer | None = None,
        vision_provider: VisionProvider | None = None,
    ) -> None:
        self.config = config or PDFParsingConfig()
        self.preflight = PDFPreflightValidator(self.config)
        self.quality = PageQualityDetector(self.config)
        self.layout = PDFLayoutAnalyzer(self.config)
        self.ocr_provider = (
            ocr_provider if ocr_provider is not None else TesseractOCRProvider(self.config)
        )
        self.region_layout = layout_detector or OpenCVLayoutDetector(self.config)
        self.table_recognizer = table_recognizer or OpenCVTableStructureRecognizer(
            self.config,
            self.ocr_provider,
        )
        self.vision_provider = vision_provider or DisabledVisionProvider()
        self.fusion = BlockFusion(self.config)

    def parse(
        self,
        content: bytes,
        filename: str,
        document_id: UUID | str | None = None,
    ) -> NativePDFDocument:
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
        text = _plain_text(pages)
        checksum = sha256(content).hexdigest()
        resolved_document_id = (
            UUID(str(document_id))
            if document_id is not None
            else uuid5(NAMESPACE_URL, f"sha256:{checksum}")
        )
        document_type = _document_type(pages)
        status = (
            PDFParseStatus.PARTIAL_SUCCESS
            if any(warning.severity is not PDFWarningSeverity.INFO for warning in warnings)
            else PDFParseStatus.SUCCEEDED
        )
        ir = DocumentIR(
            parser_version=self.config.parser_version,
            document_id=resolved_document_id,
            source_filename=filename,
            checksum_sha256=checksum,
            document_type=document_type,
            status=status,
            page_count=result.page_count,
            pages=pages,
            warnings=warnings,
            metadata={
                "file_size_bytes": len(content),
                "plain_text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "plain_text_size_bytes": len(text.encode("utf-8")),
                "source_pdf_metadata": result.metadata,
                "page_types": [page.page_type.value for page in pages],
                "page_routing": [
                    {
                        "page_number": page.page_number,
                        "page_type": page.page_type.value,
                        "route": _page_route(page),
                    }
                    for page in pages
                ],
            },
        )
        return NativePDFDocument(
            text=text,
            page_count=result.page_count,
            document_type=document_type,
            pages=pages,
            warnings=warnings,
            preflight=result,
            parser_version=self.config.parser_version,
            ir=ir,
        )

    def _extract_page(self, page: pymupdf.Page, page_number: int) -> PageIR:
        width = float(page.rect.width)
        height = float(page.rect.height)
        flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        layout: dict[str, Any] = page.get_text("dict", sort=True, flags=flags)  # type: ignore[no-untyped-call]

        native_text_candidates = self._text_candidates(layout.get("blocks", []), width, height)
        image_candidates = self._image_candidates(page, width, height)
        quality = self.quality.assess(
            text="\n".join(candidate.text or "" for candidate in native_text_candidates),
            page_width=width,
            page_height=height,
            text_bboxes=[_bbox_tuple(candidate.bbox) for candidate in native_text_candidates],
            image_bboxes=[_bbox_tuple(candidate.bbox) for candidate in image_candidates],
        )

        warnings = list(
            _quality_warnings(
                page_number,
                quality,
                include_ocr_required=not self.config.ocr_enabled,
            )
        )
        if quality.page_type in {PDFPageType.SCANNED, PDFPageType.MIXED}:
            routed = self._extract_scanned_or_mixed_page(
                page,
                page_number,
                quality,
                native_text_candidates,
            )
        else:
            routed = self._extract_native_page(
                page,
                page_number,
                native_text_candidates,
                image_candidates,
            )
        warnings.extend(routed.warnings)
        routed.candidates.sort(key=lambda candidate: (candidate.bbox.y0, candidate.bbox.x0))

        provisional_blocks = tuple(
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
            for index, candidate in enumerate(routed.candidates, start=1)
        )
        fusion = self.fusion.fuse(provisional_blocks)
        blocks = tuple(
            block.model_copy(
                update={
                    "block_id": f"p{page_number}_b{index:04d}",
                    "reading_order": index - 1,
                }
            )
            for index, block in enumerate(fusion.blocks, start=1)
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
                "routing": {
                    "scope": "page",
                    "page_type": quality.page_type.value,
                    "route": (
                        "layout_multimodal"
                        if quality.page_type in {PDFPageType.SCANNED, PDFPageType.MIXED}
                        else "native_pymupdf"
                    ),
                },
                **routed.metadata,
                "fusion": {
                    "version": self.fusion.version,
                    "duplicate_blocks_removed": fusion.duplicate_blocks_removed,
                    "table_text_blocks_removed": fusion.table_text_blocks_removed,
                    "conflicts_resolved": fusion.conflicts_resolved,
                    "output_block_count": len(blocks),
                },
            },
        )

    def _extract_native_page(
        self,
        page: pymupdf.Page,
        page_number: int,
        native_text_candidates: list[_BlockCandidate],
        image_candidates: list[_BlockCandidate],
    ) -> _RoutedExtraction:
        table_extraction = (
            extract_native_tables(page)
            if self.config.layout_enabled and self.config.layout_detect_tables
            else NativeTableExtraction(tables=())
        )
        warnings: list[ParseWarning] = []
        if table_extraction.failed:
            warnings.append(
                ParseWarning(
                    code="TABLE_DETECTION_FAILED",
                    message="Native table detection failed; positioned text was retained",
                    page_number=page_number,
                )
            )
        return _RoutedExtraction(
            candidates=[
                *native_text_candidates,
                *image_candidates,
                *_table_candidates(table_extraction),
            ],
            warnings=warnings,
            metadata={
                "layout_detection": {"requested": False, "applied": False},
                "ocr": {"requested": False, "enabled": self.config.ocr_enabled, "applied": False},
                "table_detection": {
                    "route": "native_find_tables",
                    "enabled": self.config.layout_enabled and self.config.layout_detect_tables,
                    "table_count": len(table_extraction.tables),
                    "native_table_count": len(table_extraction.tables),
                    "scanned_table_count": 0,
                    "failed": table_extraction.failed,
                },
                "vision": {"requested": False, "enabled": self.config.vlm_enabled},
            },
        )

    def _extract_scanned_or_mixed_page(
        self,
        page: pymupdf.Page,
        page_number: int,
        quality: PageQuality,
        native_text_candidates: list[_BlockCandidate],
    ) -> _RoutedExtraction:
        candidates = list(native_text_candidates)
        warnings: list[ParseWarning] = []
        layout_result: LayoutDetectionResult | None = None
        layout_error: str | None = None
        if self.config.layout_detection_enabled:
            try:
                layout_result = self.region_layout.detect(page, page_number)
            except Exception as exc:
                layout_error = type(exc).__name__
                warnings.append(
                    ParseWarning(
                        code="LAYOUT_DETECTION_FAILED",
                        message=(
                            "Page layout detection failed; whole-page OCR fallback was attempted"
                        ),
                        page_number=page_number,
                        details={"provider": self.region_layout.name, "error_type": layout_error},
                    )
                )

        text_regions = 0
        table_regions = 0
        image_regions = 0
        ocr_blocks = 0
        scanned_tables = 0
        vlm_applied = 0
        vlm_failed = 0
        regions = layout_result.regions if layout_result is not None else ()
        for region in regions:
            if region.type is LayoutRegionType.TEXT:
                text_regions += 1
                result = self._ocr_region(page, page_number, region, warnings)
                if result is not None:
                    region_candidates = _ocr_candidates(result, region)
                    candidates.extend(region_candidates)
                    ocr_blocks += len(region_candidates)
            elif region.type is LayoutRegionType.TABLE:
                table_regions += 1
                table_result = self._recognize_scanned_table(page, page_number, region, warnings)
                if table_result is not None:
                    candidates.append(_scanned_table_candidate(table_result, region))
                    scanned_tables += 1
                else:
                    result = self._ocr_region(page, page_number, region, warnings)
                    if result is not None:
                        region_candidates = _ocr_candidates(result, region)
                        candidates.extend(region_candidates)
                        ocr_blocks += len(region_candidates)
            else:
                image_regions += 1
                vision_result = self._analyze_image_region(page, page_number, region, warnings)
                if vision_result is not None:
                    vlm_applied += 1
                elif self.config.vlm_enabled:
                    vlm_failed += 1
                candidates.append(_image_region_candidate(region, vision_result))

        full_page_fallback = layout_result is None or (
            self.config.ocr_enabled
            and not any(candidate.source is PDFBlockSource.OCR for candidate in candidates)
        )
        if full_page_fallback and self.config.ocr_enabled and not _ocr_is_unavailable(warnings):
            fallback_result = self._ocr_page(page, page_number, warnings)
            if fallback_result is not None:
                fallback_candidates = _ocr_candidates(fallback_result)
                candidates.extend(fallback_candidates)
                ocr_blocks += len(fallback_candidates)

        if layout_result is not None and layout_result.fallback_used:
            warnings.append(
                ParseWarning(
                    code="LAYOUT_DETECTION_FALLBACK",
                    message=(
                        "No reliable regions were detected; the page was routed as one text region"
                    ),
                    severity=PDFWarningSeverity.INFO,
                    page_number=page_number,
                    details={"provider": layout_result.provider},
                )
            )
        if ocr_blocks:
            warnings.append(
                ParseWarning(
                    code="OCR_APPLIED",
                    message="OCR supplied positioned text for page-level layout regions",
                    severity=PDFWarningSeverity.INFO,
                    page_number=page_number,
                    details={"provider": self.ocr_provider.name, "block_count": ocr_blocks},
                )
            )
        elif self.config.ocr_enabled and not any(
            warning.code in {"OCR_REGION_FAILED", "OCR_FAILED"} for warning in warnings
        ):
            warnings.append(
                ParseWarning(
                    code="OCR_EMPTY_RESULT",
                    message="OCR completed but found no text on this page",
                    page_number=page_number,
                    details={"provider": self.ocr_provider.name},
                )
            )

        return _RoutedExtraction(
            candidates=candidates,
            warnings=warnings,
            metadata={
                "layout_detection": {
                    "requested": True,
                    "enabled": self.config.layout_detection_enabled,
                    "applied": layout_result is not None,
                    "provider": layout_result.provider
                    if layout_result
                    else self.region_layout.name,
                    "error_type": layout_error,
                    "region_count": len(regions),
                    "text_region_count": text_regions,
                    "table_region_count": table_regions,
                    "image_region_count": image_regions,
                    "fallback_used": layout_result.fallback_used if layout_result else True,
                },
                "ocr": {
                    "requested": quality.requires_ocr or quality.page_type is PDFPageType.MIXED,
                    "enabled": self.config.ocr_enabled,
                    "applied": ocr_blocks > 0,
                    "provider": self.ocr_provider.name,
                    "region_block_count": ocr_blocks,
                    "whole_page_fallback": full_page_fallback,
                },
                "table_detection": {
                    "route": "layout_tsr_cell_ocr",
                    "enabled": self.config.tsr_enabled,
                    "native_table_count": 0,
                    "scanned_table_count": scanned_tables,
                    "detected_table_region_count": table_regions,
                },
                "vision": {
                    "requested": image_regions > 0,
                    "enabled": self.config.vlm_enabled,
                    "provider": self.vision_provider.name,
                    "image_region_count": image_regions,
                    "applied_count": vlm_applied,
                    "failed_count": vlm_failed,
                },
            },
        )

    def _ocr_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        region: LayoutRegion,
        warnings: list[ParseWarning],
    ) -> OCRPageResult | None:
        if not self.config.ocr_enabled:
            return None
        if _ocr_is_unavailable(warnings):
            return None
        try:
            recognize_region = getattr(self.ocr_provider, "recognize_region", None)
            if callable(recognize_region):
                return cast(OCRPageResult, recognize_region(page, page_number, region.bbox))
            return self.ocr_provider.recognize_page(page, page_number)
        except PDFOCRError as exc:
            warnings.append(
                ParseWarning(
                    code="OCR_REGION_FAILED",
                    message="OCR could not process a detected page region",
                    page_number=page_number,
                    details={
                        "region_id": region.region_id,
                        "error_code": exc.code.value,
                        "provider": self.ocr_provider.name,
                    },
                )
            )
            return None

    def _ocr_page(
        self,
        page: pymupdf.Page,
        page_number: int,
        warnings: list[ParseWarning],
    ) -> OCRPageResult | None:
        try:
            return self.ocr_provider.recognize_page(page, page_number)
        except PDFOCRError as exc:
            warnings.append(
                ParseWarning(
                    code="OCR_FAILED",
                    message="Whole-page OCR fallback could not process this page",
                    page_number=page_number,
                    details={"error_code": exc.code.value, "provider": self.ocr_provider.name},
                )
            )
            return None

    def _recognize_scanned_table(
        self,
        page: pymupdf.Page,
        page_number: int,
        region: LayoutRegion,
        warnings: list[ParseWarning],
    ) -> ScannedTableResult | None:
        if not self.config.tsr_enabled or not self.config.ocr_enabled:
            return None
        try:
            return self.table_recognizer.recognize(page, page_number, region.bbox)
        except (PDFTableRecognitionError, PDFOCRError) as exc:
            warnings.append(
                ParseWarning(
                    code="TSR_FAILED",
                    message=(
                        "Scanned table reconstruction failed; region OCR fallback was attempted"
                    ),
                    page_number=page_number,
                    details={
                        "region_id": region.region_id,
                        "provider": self.table_recognizer.name,
                        "error_type": type(exc).__name__,
                    },
                )
            )
            return None

    def _analyze_image_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        region: LayoutRegion,
        warnings: list[ParseWarning],
    ) -> VisionRegionResult | None:
        if not self.config.vlm_enabled:
            return None
        try:
            return self.vision_provider.analyze_region(page, page_number, region.bbox)
        except PDFVisionError:
            warnings.append(
                ParseWarning(
                    code="VLM_REGION_FAILED",
                    message="VLM could not analyze a detected image region",
                    page_number=page_number,
                    details={"region_id": region.region_id, "provider": self.vision_provider.name},
                )
            )
            return None

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


def _ocr_candidates(
    result: OCRPageResult,
    region: LayoutRegion | None = None,
) -> list[_BlockCandidate]:
    return [
        _BlockCandidate(
            bbox=block.bbox,
            type=PDFBlockType.TEXT,
            text=block.text,
            raw_text=block.text,
            source=PDFBlockSource.OCR,
            confidence=block.confidence,
            table_markdown=None,
            metadata={
                **block.metadata,
                **(
                    {
                        "layout_region_id": region.region_id,
                        "layout_region_type": region.type.value,
                    }
                    if region is not None
                    else {"ocr_scope": "whole_page"}
                ),
            },
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


def _ocr_is_unavailable(warnings: list[ParseWarning]) -> bool:
    return any(
        warning.code in {"OCR_REGION_FAILED", "OCR_FAILED"}
        and warning.details.get("error_code") == "PDF_OCR_UNAVAILABLE"
        for warning in warnings
    )


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


def _scanned_table_candidate(
    result: ScannedTableResult,
    region: LayoutRegion,
) -> _BlockCandidate:
    return _BlockCandidate(
        bbox=result.bbox,
        type=PDFBlockType.TABLE,
        text=None,
        raw_text=None,
        source=PDFBlockSource.DERIVED,
        confidence=region.confidence,
        table_markdown=result.markdown,
        metadata={
            **result.metadata,
            "layout_region_id": region.region_id,
            "layout_region_type": region.type.value,
            "tsr_provider": result.provider,
        },
    )


def _image_region_candidate(
    region: LayoutRegion,
    vision: VisionRegionResult | None,
) -> _BlockCandidate:
    metadata: dict[str, JsonValue] = {
        **region.metadata,
        "layout_region_id": region.region_id,
        "layout_region_type": region.type.value,
    }
    text: str | None = None
    if vision is not None:
        text = vision.caption
        metadata.update(
            {
                **vision.metadata,
                "vision_provider": vision.provider,
                "vision_model": vision.model,
                "visible_text": vision.visible_text,
            }
        )
    return _BlockCandidate(
        bbox=region.bbox,
        type=PDFBlockType.IMAGE,
        text=text,
        raw_text=vision.visible_text if vision is not None else None,
        source=PDFBlockSource.DERIVED,
        confidence=region.confidence,
        table_markdown=None,
        metadata=metadata,
    )


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


def _page_route(page: PageIR) -> JsonValue:
    routing = page.metadata.get("routing")
    return routing.get("route") if isinstance(routing, dict) else None


def _document_type(pages: tuple[PageIR, ...]) -> PDFDocumentType:
    page_types = {page.page_type for page in pages if page.page_type is not PDFPageType.EMPTY}
    if not page_types or page_types == {PDFPageType.TEXT}:
        return PDFDocumentType.TEXT_BASED
    if page_types == {PDFPageType.SCANNED}:
        return PDFDocumentType.SCANNED
    return PDFDocumentType.MIXED
