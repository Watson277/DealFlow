import pytest

from app.documents.pdf import PageQuality, PageQualityDetector, PDFPageType, PDFParsingConfig


def assess(
    text: str,
    *,
    text_bboxes: list[tuple[float, float, float, float]] | None = None,
    image_bboxes: list[tuple[float, float, float, float]] | None = None,
) -> PageQuality:
    return PageQualityDetector(PDFParsingConfig()).assess(
        text=text,
        page_width=100,
        page_height=100,
        text_bboxes=text_bboxes or [],
        image_bboxes=image_bboxes or [],
    )


def test_quality_classifies_native_text_page() -> None:
    quality = assess(
        "Reliable native text for a customer requirement",
        text_bboxes=[(10, 10, 90, 30)],
    )

    assert quality.page_type is PDFPageType.TEXT
    assert quality.requires_ocr is False
    assert quality.effective_char_count > 20
    assert quality.text_coverage == pytest.approx(0.16)


def test_quality_classifies_scanned_and_empty_pages() -> None:
    scanned = assess("", image_bboxes=[(0, 0, 100, 100)])
    empty = assess("")

    assert scanned.page_type is PDFPageType.SCANNED
    assert scanned.requires_ocr is True
    assert scanned.image_coverage == 1.0
    assert empty.page_type is PDFPageType.EMPTY
    assert empty.requires_ocr is False


def test_quality_classifies_mixed_page_without_forcing_ocr() -> None:
    quality = assess(
        "Native text remains useful alongside a large architecture diagram.",
        text_bboxes=[(10, 10, 90, 30)],
        image_bboxes=[(0, 40, 100, 90)],
    )

    assert quality.page_type is PDFPageType.MIXED
    assert quality.requires_ocr is False


def test_quality_routes_sparse_or_garbled_content_to_ocr() -> None:
    sparse = assess("Page 1", image_bboxes=[(0, 0, 100, 100)])
    garbled = assess("valid���", text_bboxes=[(0, 0, 30, 10)])

    assert sparse.page_type is PDFPageType.SCANNED
    assert sparse.requires_ocr is True
    assert garbled.page_type is PDFPageType.SCANNED
    assert garbled.requires_ocr is True
    assert garbled.garbled_ratio > 0.1


def test_coverage_uses_union_instead_of_double_counting_overlap() -> None:
    quality = assess(
        "Readable native content long enough for classification",
        text_bboxes=[(0, 0, 60, 100), (40, 0, 100, 100)],
    )

    assert quality.text_coverage == 1.0
