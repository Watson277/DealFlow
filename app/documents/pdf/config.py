"""Local preflight and page classification only; parsing is performed by MinerU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class PDFParsingConfig:
    max_pages: int = 500
    min_effective_chars: int = 20
    max_garbled_ratio: float = 0.10
    scanned_image_coverage_threshold: float = 0.60
    mixed_image_coverage_threshold: float = 0.35
    significant_image_min_area_ratio: float = 0.02
    significant_image_min_width_ratio: float = 0.20
    significant_image_min_height_ratio: float = 0.08

    def __post_init__(self) -> None:
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
        if self.mixed_image_coverage_threshold > self.scanned_image_coverage_threshold:
            raise ValueError("mixed_image_coverage_threshold must not exceed the scanned threshold")

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            max_pages=settings.pdf_max_pages,
            min_effective_chars=settings.pdf_text_min_effective_chars,
            max_garbled_ratio=settings.pdf_text_max_garbled_ratio,
            scanned_image_coverage_threshold=settings.pdf_scanned_image_coverage_threshold,
            mixed_image_coverage_threshold=settings.pdf_mixed_image_coverage_threshold,
            significant_image_min_area_ratio=settings.pdf_significant_image_min_area_ratio,
            significant_image_min_width_ratio=settings.pdf_significant_image_min_width_ratio,
            significant_image_min_height_ratio=settings.pdf_significant_image_min_height_ratio,
        )
