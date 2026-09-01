import subprocess

import pymupdf
import pytest

from app.documents.parser import DocumentParser
from app.documents.pdf import (
    BoundingBox,
    NativePDFParser,
    OCRBlock,
    OCRPageResult,
    PDFBlockSource,
    PDFOCRError,
    PDFOCRErrorCode,
    PDFPageType,
    PDFParsingConfig,
    TesseractOCRProvider,
)
from app.documents.pdf import ocr as ocr_module


def scanned_pdf_bytes() -> bytes:
    source = pymupdf.open()
    source_page = source.new_page(width=200, height=300)
    source_page.insert_text((20, 80), "DealFlow OCR requirement", fontsize=14)
    pixmap = source_page.get_pixmap(dpi=150, colorspace=pymupdf.csRGB, alpha=False)

    scanned = pymupdf.open()
    scanned_page = scanned.new_page(width=200, height=300)
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
    content = scanned.tobytes()
    scanned.close()
    source.close()
    return content


class FakeOCRProvider:
    name = "fake-ocr"

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        assert page_number == 1
        return OCRPageResult(
            blocks=(
                OCRBlock(
                    text="必须支持审计日志 DealFlow",
                    bbox=BoundingBox(x0=20, y0=50, x1=180, y1=85),
                    confidence=0.94,
                    metadata={"ocr_provider": self.name},
                ),
            ),
            provider=self.name,
            rendered_width=694,
            rendered_height=1042,
            dpi=250,
            languages="chi_sim+eng",
        )


class UnavailableOCRProvider:
    name = "missing-ocr"

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        raise PDFOCRError(PDFOCRErrorCode.UNAVAILABLE, "runtime unavailable")


def test_document_parser_uses_ocr_for_scanned_page() -> None:
    parser = DocumentParser(PDFParsingConfig(), FakeOCRProvider())

    parsed = parser.parse(scanned_pdf_bytes(), "scan.pdf")

    assert "必须支持审计日志 DealFlow" in parsed.text
    assert parsed.pdf is not None
    page = parsed.pdf.pages[0]
    assert page.page_type is PDFPageType.SCANNED
    ocr_blocks = [block for block in page.blocks if block.source is PDFBlockSource.OCR]
    assert len(ocr_blocks) == 1
    assert ocr_blocks[0].confidence == pytest.approx(0.94)
    assert ocr_blocks[0].bbox.x1 <= page.width
    assert page.metadata["ocr"]["applied"] is True
    assert [warning.code for warning in page.warnings] == ["OCR_APPLIED"]


def test_tesseract_provider_maps_pixels_to_pdf_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t100\t200\t80\t30\t95.0\t审计",
            "5\t1\t1\t1\t1\t2\t185\t200\t100\t30\t85.0\tlogs",
        ]
    )
    monkeypatch.setattr(ocr_module.shutil, "which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr(
        ocr_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, tsv.encode(), b""),
    )
    document = pymupdf.open()
    page = document.new_page(width=200, height=300)
    provider = TesseractOCRProvider(PDFParsingConfig(ocr_dpi=250))

    result = provider.recognize_page(page, 1)

    pixmap = page.get_pixmap(dpi=250, colorspace=pymupdf.csRGB, alpha=False)
    assert result.blocks[0].text == "审计logs"
    assert result.blocks[0].confidence == pytest.approx(0.9)
    assert result.blocks[0].bbox.x0 == pytest.approx(100 * 200 / pixmap.width)
    assert result.blocks[0].bbox.y0 == pytest.approx(200 * 300 / pixmap.height)
    assert result.blocks[0].bbox.x1 <= 200
    assert result.blocks[0].bbox.y1 <= 300
    document.close()


def test_tesseract_provider_maps_region_pixels_to_page_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t0\t0\t100\t50\t90.0\tregion",
        ]
    )
    monkeypatch.setattr(ocr_module.shutil, "which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr(
        ocr_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, tsv.encode(), b""),
    )
    document = pymupdf.open()
    page = document.new_page(width=200, height=300)
    bbox = BoundingBox(x0=50, y0=75, x1=150, y1=225)

    result = TesseractOCRProvider(PDFParsingConfig(ocr_dpi=250)).recognize_region(page, 1, bbox)

    document.close()
    assert result.blocks[0].bbox.x0 == pytest.approx(50)
    assert result.blocks[0].bbox.y0 == pytest.approx(75)
    assert 50 < result.blocks[0].bbox.x1 <= 150
    assert 75 < result.blocks[0].bbox.y1 <= 225


def test_tesseract_provider_reports_missing_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_module.shutil, "which", lambda _: None)
    document = pymupdf.open()
    page = document.new_page()

    with pytest.raises(PDFOCRError) as captured:
        TesseractOCRProvider(PDFParsingConfig()).recognize_page(page, 1)

    document.close()
    assert captured.value.code is PDFOCRErrorCode.UNAVAILABLE


def test_tesseract_provider_splits_one_ocr_line_at_a_column_gutter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t100\t200\t120\t40\t96.0\tLeft",
            "5\t1\t1\t1\t1\t2\t235\t200\t180\t40\t94.0\trequirement",
            "5\t1\t1\t1\t1\t3\t1250\t200\t130\t40\t95.0\tRight",
            "5\t1\t1\t1\t1\t4\t1395\t200\t150\t40\t93.0\tevidence",
        ]
    )
    monkeypatch.setattr(ocr_module.shutil, "which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr(
        ocr_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, tsv.encode(), b""),
    )
    document = pymupdf.open()
    page = document.new_page(width=600, height=500)

    result = TesseractOCRProvider(PDFParsingConfig(ocr_dpi=250)).recognize_page(page, 1)

    document.close()
    assert [block.text for block in result.blocks] == ["Left requirement", "Right evidence"]
    assert result.blocks[0].metadata["ocr_line_segment"] == 1
    assert result.blocks[1].metadata["ocr_line_segment"] == 2
    assert result.blocks[0].bbox.x1 < result.blocks[1].bbox.x0


def test_parser_retains_native_page_and_stable_warning_when_ocr_fails() -> None:
    parsed = NativePDFParser(PDFParsingConfig(), UnavailableOCRProvider()).parse(
        scanned_pdf_bytes(),
        "scan.pdf",
    )

    page = parsed.pages[0]
    assert not [block for block in page.blocks if block.source is PDFBlockSource.OCR]
    assert [warning.code for warning in page.warnings] == ["OCR_REGION_FAILED"]
    assert page.warnings[0].details == {
        "region_id": "p1_r0001",
        "error_code": "PDF_OCR_UNAVAILABLE",
        "provider": "missing-ocr",
    }
    assert page.metadata["ocr"]["applied"] is False
