import pymupdf
import pytest

from app.core.config import Settings
from app.documents.pdf import (
    NativePDFParser,
    PDFParsingConfig,
    PDFPreflightCode,
    PDFPreflightError,
)
from app.documents.pdf.preflight import PDFPreflightValidator


def pdf_bytes(*, pages: int = 1, password: str | None = None) -> bytes:
    document = pymupdf.open()
    for _ in range(pages):
        document.new_page()
    if password:
        content = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner-password",
            user_pw=password,
        )
    else:
        content = document.tobytes()
    document.close()
    return content


def test_preflight_preserves_file_and_pdf_metadata() -> None:
    document = pymupdf.open()
    document.new_page()
    document.set_metadata({"title": "DealFlow requirements"})
    content = document.tobytes()
    document.close()

    parsed = NativePDFParser().parse(content, "request.pdf")

    assert parsed.preflight.filename == "request.pdf"
    assert parsed.preflight.file_size_bytes == len(content)
    assert parsed.preflight.page_count == 1
    assert parsed.preflight.metadata["title"] == "DealFlow requirements"


@pytest.mark.parametrize("content", [b"", b"not a PDF", b"%PDF-1.7\ncorrupted"])
def test_preflight_rejects_invalid_pdf(content: bytes) -> None:
    with pytest.raises(PDFPreflightError) as captured:
        NativePDFParser().parse(content, "broken.pdf")

    assert captured.value.code is PDFPreflightCode.INVALID


def test_preflight_rejects_password_protected_pdf() -> None:
    with pytest.raises(PDFPreflightError) as captured:
        NativePDFParser().parse(pdf_bytes(password="secret"), "protected.pdf")

    assert captured.value.code is PDFPreflightCode.ENCRYPTED


def test_preflight_rejects_zero_pages_and_page_limit() -> None:
    empty = pymupdf.open()
    with pytest.raises(PDFPreflightError) as captured:
        PDFPreflightValidator(PDFParsingConfig()).validate(
            empty,
            filename="empty.pdf",
            file_size_bytes=0,
        )
    empty.close()
    assert captured.value.code is PDFPreflightCode.EMPTY

    parser = NativePDFParser(PDFParsingConfig(max_pages=1))
    with pytest.raises(PDFPreflightError) as captured:
        parser.parse(pdf_bytes(pages=2), "large.pdf")
    assert captured.value.code is PDFPreflightCode.PAGE_LIMIT_EXCEEDED


def test_pdf_config_loads_from_application_settings() -> None:
    settings = Settings(
        _env_file=None,
        pdf_parser_version="native-test",
        pdf_max_pages=12,
        pdf_text_min_effective_chars=8,
        pdf_text_max_garbled_ratio=0.2,
        pdf_scanned_image_coverage_threshold=0.7,
        pdf_mixed_image_coverage_threshold=0.4,
        pdf_ocr_enabled=False,
        pdf_ocr_dpi=300,
        pdf_ocr_languages="eng",
        pdf_ocr_timeout_seconds=45,
        pdf_ocr_executable="custom-tesseract",
        pdf_ocr_page_segmentation_mode=6,
        pdf_layout_enabled=False,
        pdf_layout_detect_tables=False,
        pdf_layout_header_footer_margin_ratio=0.1,
        pdf_layout_repeated_region_min_fraction=0.75,
        pdf_layout_column_gap_ratio=0.08,
        pdf_layout_paragraph_gap_multiplier=1.2,
        pdf_layout_title_font_ratio=1.4,
    )

    config = PDFParsingConfig.from_settings(settings)

    assert config == PDFParsingConfig(
        parser_version="native-test",
        max_pages=12,
        min_effective_chars=8,
        max_garbled_ratio=0.2,
        scanned_image_coverage_threshold=0.7,
        mixed_image_coverage_threshold=0.4,
        ocr_enabled=False,
        ocr_dpi=300,
        ocr_languages="eng",
        ocr_timeout_seconds=45,
        ocr_executable="custom-tesseract",
        ocr_page_segmentation_mode=6,
        layout_enabled=False,
        layout_detect_tables=False,
        layout_header_footer_margin_ratio=0.1,
        layout_repeated_region_min_fraction=0.75,
        layout_column_gap_ratio=0.08,
        layout_paragraph_gap_multiplier=1.2,
        layout_title_font_ratio=1.4,
    )


def test_pdf_config_rejects_inconsistent_thresholds() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        PDFParsingConfig(
            scanned_image_coverage_threshold=0.4,
            mixed_image_coverage_threshold=0.5,
        )
