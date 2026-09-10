"""Configuration for native PDF extraction, OCR, and layout analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self

if TYPE_CHECKING:
    from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class PDFParsingConfig:
    parser_version: str = "page-routing-layout-2.2"
    max_pages: int = 500
    min_effective_chars: int = 20
    max_garbled_ratio: float = 0.10
    scanned_image_coverage_threshold: float = 0.60
    mixed_image_coverage_threshold: float = 0.35
    significant_image_min_area_ratio: float = 0.02
    significant_image_min_width_ratio: float = 0.20
    significant_image_min_height_ratio: float = 0.08
    ocr_enabled: bool = True
    ocr_provider: Literal["tesseract", "paddleocr"] = "tesseract"
    ocr_dpi: int = 250
    ocr_languages: str = "chi_sim+eng"
    ocr_timeout_seconds: float = 120.0
    ocr_executable: str = "tesseract"
    ocr_page_segmentation_mode: int = 3
    paddle_ocr_url: str = "http://paddleocr:8080/v1/ocr"
    paddle_ocr_model: str = "PP-OCRv6_medium"
    paddle_ocr_timeout_seconds: float = 120.0
    paddle_ocr_batch_size: int = 32
    ocr_fallback_enabled: bool = True
    layout_enabled: bool = True
    layout_detect_tables: bool = True
    layout_header_footer_margin_ratio: float = 0.12
    layout_repeated_region_min_fraction: float = 0.60
    layout_column_gap_ratio: float = 0.06
    layout_paragraph_gap_multiplier: float = 1.40
    layout_title_font_ratio: float = 1.25
    layout_detection_enabled: bool = True
    layout_detection_dpi: int = 250
    layout_min_region_area_ratio: float = 0.001
    tsr_enabled: bool = True
    tsr_max_cells: int = 200
    vlm_enabled: bool = False
    fusion_iou_threshold: float = 0.55
    fusion_text_similarity_threshold: float = 0.88
    fusion_table_text_overlap_threshold: float = 0.50
    page_parallel_enabled: bool = True
    page_workers: int = 4
    page_parallel_min_pages: int = 4

    def __post_init__(self) -> None:
        if not self.parser_version.strip():
            raise ValueError("parser_version must not be blank")
        if self.ocr_provider not in {"tesseract", "paddleocr"}:
            raise ValueError("ocr_provider must be tesseract or paddleocr")
        if self.max_pages < 1:
            raise ValueError("max_pages must be positive")
        if self.min_effective_chars < 1:
            raise ValueError("min_effective_chars must be positive")
        for name, value in (
            ("max_garbled_ratio", self.max_garbled_ratio),
            ("scanned_image_coverage_threshold", self.scanned_image_coverage_threshold),
            ("mixed_image_coverage_threshold", self.mixed_image_coverage_threshold),
            ("significant_image_min_area_ratio", self.significant_image_min_area_ratio),
            ("significant_image_min_width_ratio", self.significant_image_min_width_ratio),
            ("significant_image_min_height_ratio", self.significant_image_min_height_ratio),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if not 1 <= self.page_workers <= 16:
            raise ValueError("page_workers must be between one and 16")
        if self.page_parallel_min_pages < 2:
            raise ValueError("page_parallel_min_pages must be at least two")
        if self.mixed_image_coverage_threshold > self.scanned_image_coverage_threshold:
            raise ValueError("mixed_image_coverage_threshold must not exceed the scanned threshold")
        if not 72 <= self.ocr_dpi <= 600:
            raise ValueError("ocr_dpi must be between 72 and 600")
        if not self.ocr_languages.strip():
            raise ValueError("ocr_languages must not be blank")
        if self.ocr_timeout_seconds <= 0:
            raise ValueError("ocr_timeout_seconds must be positive")
        if not self.ocr_executable.strip():
            raise ValueError("ocr_executable must not be blank")
        if not 0 <= self.ocr_page_segmentation_mode <= 13:
            raise ValueError("ocr_page_segmentation_mode must be between 0 and 13")
        if not self.paddle_ocr_url.strip():
            raise ValueError("paddle_ocr_url must not be blank")
        if not self.paddle_ocr_model.strip():
            raise ValueError("paddle_ocr_model must not be blank")
        if self.paddle_ocr_timeout_seconds <= 0:
            raise ValueError("paddle_ocr_timeout_seconds must be positive")
        if not 1 <= self.paddle_ocr_batch_size <= 256:
            raise ValueError("paddle_ocr_batch_size must be between one and 256")
        for name, value in (
            ("layout_header_footer_margin_ratio", self.layout_header_footer_margin_ratio),
            ("layout_repeated_region_min_fraction", self.layout_repeated_region_min_fraction),
            ("layout_column_gap_ratio", self.layout_column_gap_ratio),
        ):
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if self.layout_header_footer_margin_ratio >= 0.5:
            raise ValueError("layout_header_footer_margin_ratio must be less than 0.5")
        if self.layout_paragraph_gap_multiplier <= 0:
            raise ValueError("layout_paragraph_gap_multiplier must be positive")
        if self.layout_title_font_ratio <= 1:
            raise ValueError("layout_title_font_ratio must be greater than one")
        if not 72 <= self.layout_detection_dpi <= 600:
            raise ValueError("layout_detection_dpi must be between 72 and 600")
        if not 0.0 < self.layout_min_region_area_ratio < 1.0:
            raise ValueError("layout_min_region_area_ratio must be between zero and one")
        if self.tsr_max_cells < 1:
            raise ValueError("tsr_max_cells must be positive")
        for name, value in (
            ("fusion_iou_threshold", self.fusion_iou_threshold),
            ("fusion_text_similarity_threshold", self.fusion_text_similarity_threshold),
            ("fusion_table_text_overlap_threshold", self.fusion_table_text_overlap_threshold),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            parser_version=settings.pdf_parser_version,
            max_pages=settings.pdf_max_pages,
            min_effective_chars=settings.pdf_text_min_effective_chars,
            max_garbled_ratio=settings.pdf_text_max_garbled_ratio,
            scanned_image_coverage_threshold=settings.pdf_scanned_image_coverage_threshold,
            mixed_image_coverage_threshold=settings.pdf_mixed_image_coverage_threshold,
            significant_image_min_area_ratio=settings.pdf_significant_image_min_area_ratio,
            significant_image_min_width_ratio=settings.pdf_significant_image_min_width_ratio,
            significant_image_min_height_ratio=settings.pdf_significant_image_min_height_ratio,
            ocr_enabled=settings.pdf_ocr_enabled,
            ocr_provider=settings.pdf_ocr_provider,
            ocr_dpi=settings.pdf_ocr_dpi,
            ocr_languages=settings.pdf_ocr_languages,
            ocr_timeout_seconds=settings.pdf_ocr_timeout_seconds,
            ocr_executable=settings.pdf_ocr_executable,
            ocr_page_segmentation_mode=settings.pdf_ocr_page_segmentation_mode,
            paddle_ocr_url=settings.pdf_paddle_ocr_url,
            paddle_ocr_model=settings.pdf_paddle_ocr_model,
            paddle_ocr_timeout_seconds=settings.pdf_paddle_ocr_timeout_seconds,
            paddle_ocr_batch_size=settings.pdf_paddle_ocr_batch_size,
            ocr_fallback_enabled=settings.pdf_ocr_fallback_enabled,
            layout_enabled=settings.pdf_layout_enabled,
            layout_detect_tables=settings.pdf_layout_detect_tables,
            layout_header_footer_margin_ratio=settings.pdf_layout_header_footer_margin_ratio,
            layout_repeated_region_min_fraction=settings.pdf_layout_repeated_region_min_fraction,
            layout_column_gap_ratio=settings.pdf_layout_column_gap_ratio,
            layout_paragraph_gap_multiplier=settings.pdf_layout_paragraph_gap_multiplier,
            layout_title_font_ratio=settings.pdf_layout_title_font_ratio,
            layout_detection_enabled=settings.pdf_layout_detection_enabled,
            layout_detection_dpi=settings.pdf_layout_detection_dpi,
            layout_min_region_area_ratio=settings.pdf_layout_min_region_area_ratio,
            tsr_enabled=settings.pdf_tsr_enabled,
            tsr_max_cells=settings.pdf_tsr_max_cells,
            vlm_enabled=settings.pdf_vlm_enabled,
            fusion_iou_threshold=settings.pdf_fusion_iou_threshold,
            fusion_text_similarity_threshold=settings.pdf_fusion_text_similarity_threshold,
            fusion_table_text_overlap_threshold=settings.pdf_fusion_table_text_overlap_threshold,
            page_parallel_enabled=settings.pdf_page_parallel_enabled,
            page_workers=settings.pdf_page_workers,
            page_parallel_min_pages=settings.pdf_page_parallel_min_pages,
        )
