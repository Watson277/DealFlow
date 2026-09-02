import base64

import pymupdf
import pytest

from app.core.exceptions import DocumentProcessingError
from app.documents.parser import DocumentParser
from app.documents.pdf import (
    NativePDFParser,
    PDFBlockSource,
    PDFBlockType,
    PDFDocumentType,
    PDFPageType,
    PDFParsingConfig,
)

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_native_parser_extracts_text_image_layout_and_bboxes() -> None:
    document = pymupdf.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((30, 50), "DealFlow native requirement", fontsize=14)
    page.insert_text((30, 130), "Audit logs must be retained.", fontsize=10)
    page.insert_image(pymupdf.Rect(250, 350, 280, 380), stream=ONE_PIXEL_PNG)
    content = document.tobytes()
    document.close()

    parsed = NativePDFParser().parse(content, "request.pdf")

    assert parsed.document_type is PDFDocumentType.TEXT_BASED
    assert parsed.page_count == 1
    assert parsed.parser_version == "page-routing-layout-2.1"
    assert "--- Page 1 ---" in parsed.text
    assert "DealFlow native requirement" in parsed.text

    result_page = parsed.pages[0]
    assert result_page.page_type is PDFPageType.TEXT
    assert result_page.metadata["routing"]["route"] == "native_pymupdf"
    assert result_page.width == pytest.approx(300)
    assert result_page.height == pytest.approx(400)
    assert [block.reading_order for block in result_page.blocks] == list(
        range(len(result_page.blocks))
    )
    assert all(block.source is PDFBlockSource.NATIVE for block in result_page.blocks)

    text_blocks = [block for block in result_page.blocks if block.type is PDFBlockType.TEXT]
    image_blocks = [block for block in result_page.blocks if block.type is PDFBlockType.IMAGE]
    assert len(text_blocks) == 2
    assert len(image_blocks) == 1
    assert text_blocks[0].bbox.x0 == pytest.approx(30)
    assert 0 <= text_blocks[0].bbox.y0 < text_blocks[0].bbox.y1 <= result_page.height
    font_names = text_blocks[0].metadata["font_names"]
    assert isinstance(font_names, list)
    assert "Helvetica" in font_names
    assert image_blocks[0].bbox.model_dump() == {
        "x0": 250.0,
        "y0": 350.0,
        "x1": 280.0,
        "y1": 380.0,
    }
    assert "image" not in image_blocks[0].metadata


def test_native_parser_classifies_scanned_and_mixed_documents() -> None:
    document = pymupdf.open()
    scanned = document.new_page(width=200, height=300)
    scanned.insert_image(scanned.rect, stream=ONE_PIXEL_PNG)
    text = document.new_page(width=200, height=300)
    text.insert_text((20, 50), "A complete native text requirement for deployment.")
    content = document.tobytes()
    document.close()

    parsed = NativePDFParser(PDFParsingConfig(ocr_enabled=False)).parse(content, "mixed.pdf")

    assert parsed.document_type is PDFDocumentType.MIXED
    assert [page.page_type for page in parsed.pages] == [PDFPageType.SCANNED, PDFPageType.TEXT]
    assert parsed.ir.metadata["page_types"] == ["scanned", "text"]
    quality_metadata = parsed.pages[0].metadata["quality"]
    assert isinstance(quality_metadata, dict)
    assert quality_metadata["requires_ocr"] is True
    assert parsed.pages[0].warnings[0].code == "OCR_REQUIRED"
    assert "complete native text requirement" in parsed.text


def test_document_parser_keeps_text_compatibility_and_exposes_pdf_ir() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Structured PDF requirement")
    content = document.tobytes()
    document.close()

    parsed = DocumentParser().parse(content, "request.pdf")

    assert "Structured PDF requirement" in parsed.text
    assert parsed.pdf is not None
    assert parsed.pdf.pages[0].blocks[0].bbox.x0 == pytest.approx(72)


def test_document_parser_still_rejects_pdf_with_no_native_text() -> None:
    document = pymupdf.open()
    scanned = document.new_page(width=200, height=300)
    scanned.insert_image(scanned.rect, stream=ONE_PIXEL_PNG)
    content = document.tobytes()
    document.close()

    config = PDFParsingConfig(ocr_enabled=False)
    native = NativePDFParser(config).parse(content, "scan.pdf")
    assert native.document_type is PDFDocumentType.SCANNED
    assert native.pages[0].warnings[0].code == "OCR_REQUIRED"

    with pytest.raises(DocumentProcessingError, match="no extractable text"):
        DocumentParser(config).parse(content, "scan.pdf")
