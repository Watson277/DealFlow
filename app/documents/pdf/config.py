"""Configuration for native PDF inspection, extraction, and OCR fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class PDFParsingConfig:
    parser_version: str = "native-ocr-1.0"
    max_pages: int = 500
    min_effective_chars: int = 20
    max_garbled_ratio: float = 0.10
    scanned_image_coverage_threshold: float = 0.60
    mixed_image_coverage_threshold: float = 0.35
    ocr_enabled: bool = True
    ocr_dpi: int = 250
    ocr_languages: str = "chi_sim+eng"
    ocr_timeout_seconds: float = 120.0
    ocr_executable: str = "tesseract"
    ocr_page_segmentation_mode: int = 3

    def __post_init__(self) -> None:
        if not self.parser_version.strip():
            raise ValueError("parser_version must not be blank")
        if self.max_pages < 1:
            raise ValueError("max_pages must be positive")
        if self.min_effective_chars < 1:
            raise ValueError("min_effective_chars must be positive")
        for name, value in (
            ("max_garbled_ratio", self.max_garbled_ratio),
            ("scanned_image_coverage_threshold", self.scanned_image_coverage_threshold),
            ("mixed_image_coverage_threshold", self.mixed_image_coverage_threshold),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")
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

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            parser_version=settings.pdf_parser_version,
            max_pages=settings.pdf_max_pages,
            min_effective_chars=settings.pdf_text_min_effective_chars,
            max_garbled_ratio=settings.pdf_text_max_garbled_ratio,
            scanned_image_coverage_threshold=settings.pdf_scanned_image_coverage_threshold,
            mixed_image_coverage_threshold=settings.pdf_mixed_image_coverage_threshold,
            ocr_enabled=settings.pdf_ocr_enabled,
            ocr_dpi=settings.pdf_ocr_dpi,
            ocr_languages=settings.pdf_ocr_languages,
            ocr_timeout_seconds=settings.pdf_ocr_timeout_seconds,
            ocr_executable=settings.pdf_ocr_executable,
            ocr_page_segmentation_mode=settings.pdf_ocr_page_segmentation_mode,
        )
