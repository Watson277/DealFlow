import pymupdf

from app.documents.pdf import (
    BoundingBox,
    LayoutDetectionResult,
    LayoutRegion,
    LayoutRegionType,
    NativePDFParser,
    OCRBlock,
    OCRPageResult,
    OpenCVLayoutDetector,
    OpenCVTableStructureRecognizer,
    PDFBlockSource,
    PDFBlockType,
    PDFPageType,
    PDFParsingConfig,
    ScannedTableResult,
    VisionRegionResult,
)


def _scanned_page_bytes() -> bytes:
    source = pymupdf.open()
    source_page = source.new_page(width=200, height=300)
    source_page.insert_text((20, 70), "scanned requirement", fontsize=14)
    pixmap = source_page.get_pixmap(dpi=150, colorspace=pymupdf.csRGB, alpha=False)

    scanned = pymupdf.open()
    page = scanned.new_page(width=200, height=300)
    page.insert_image(page.rect, stream=pixmap.tobytes("png"))
    content = scanned.tobytes()
    scanned.close()
    source.close()
    return content


class FakeLayoutDetector:
    name = "fake-layout"

    def detect(self, page: pymupdf.Page, page_number: int) -> LayoutDetectionResult:
        assert page_number == 1
        return LayoutDetectionResult(
            regions=(
                LayoutRegion(
                    region_id="p1_r0001",
                    type=LayoutRegionType.TEXT,
                    bbox=BoundingBox(x0=10, y0=40, x1=190, y1=90),
                    confidence=0.95,
                    metadata={},
                ),
                LayoutRegion(
                    region_id="p1_r0002",
                    type=LayoutRegionType.TABLE,
                    bbox=BoundingBox(x0=10, y0=110, x1=190, y1=190),
                    confidence=0.92,
                    metadata={},
                ),
                LayoutRegion(
                    region_id="p1_r0003",
                    type=LayoutRegionType.IMAGE,
                    bbox=BoundingBox(x0=10, y0=210, x1=190, y1=285),
                    confidence=0.90,
                    metadata={},
                ),
            ),
            provider=self.name,
            rendered_width=500,
            rendered_height=750,
            dpi=180,
        )


class FakeRegionOCR:
    name = "fake-region-ocr"

    def __init__(self) -> None:
        self.regions: list[BoundingBox] = []

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult:
        self.regions.append(bbox)
        return OCRPageResult(
            blocks=(
                OCRBlock(
                    text="Region OCR requirement",
                    bbox=bbox,
                    confidence=0.96,
                    metadata={"ocr_scope": "region"},
                ),
            ),
            provider=self.name,
            rendered_width=450,
            rendered_height=125,
            dpi=250,
            languages="eng",
        )

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        raise AssertionError("whole-page OCR must not run when region OCR succeeds")


class FakeTableRecognizer:
    name = "fake-tsr"

    def recognize(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> ScannedTableResult:
        return ScannedTableResult(
            bbox=bbox,
            markdown="| Capability | Status |\n| --- | --- |\n| Audit | Supported |",
            provider=self.name,
            row_count=2,
            column_count=2,
            metadata={"cell_count": 4},
        )


class FakeVisionProvider:
    name = "fake-vlm"

    def analyze_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> VisionRegionResult:
        return VisionRegionResult(
            caption="Architecture diagram",
            visible_text="API Gateway",
            provider=self.name,
            model="fake-vision-model",
            metadata={"verified": True},
        )


def test_scanned_page_routes_regions_to_ocr_tsr_and_vlm() -> None:
    ocr = FakeRegionOCR()
    parsed = NativePDFParser(
        PDFParsingConfig(vlm_enabled=True),
        ocr_provider=ocr,
        layout_detector=FakeLayoutDetector(),
        table_recognizer=FakeTableRecognizer(),
        vision_provider=FakeVisionProvider(),
    ).parse(_scanned_page_bytes(), "scan.pdf")

    page = parsed.pages[0]
    assert page.page_type is PDFPageType.SCANNED
    assert page.metadata["routing"]["route"] == "layout_multimodal"
    assert len(ocr.regions) == 1
    assert [block.type for block in page.blocks] == [
        PDFBlockType.TEXT,
        PDFBlockType.TABLE,
        PDFBlockType.IMAGE,
    ]
    assert page.blocks[0].source is PDFBlockSource.OCR
    assert page.blocks[1].table_markdown is not None
    assert page.blocks[2].text == "Architecture diagram"
    assert page.metadata["table_detection"]["scanned_table_count"] == 1
    assert page.metadata["vision"]["applied_count"] == 1
    assert parsed.ir.metadata["page_routing"] == [
        {"page_number": 1, "page_type": "scanned", "route": "layout_multimodal"}
    ]


class CellOCR:
    name = "cell-ocr"

    def __init__(self) -> None:
        self.calls = 0

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult:
        self.calls += 1
        return OCRPageResult(
            blocks=(
                OCRBlock(
                    text=f"cell-{self.calls}",
                    bbox=bbox,
                    confidence=0.9,
                    metadata={},
                ),
            ),
            provider=self.name,
            rendered_width=100,
            rendered_height=50,
            dpi=250,
            languages="eng",
        )

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        raise AssertionError("TSR must OCR cells, not the whole page")


def test_opencv_detects_ruled_table_and_tsr_ocrs_each_cell() -> None:
    document = pymupdf.open()
    page = document.new_page(width=400, height=250)
    for x in (40, 190, 340):
        page.draw_line((x, 50), (x, 170), width=2)
    for y in (50, 110, 170):
        page.draw_line((40, y), (340, y), width=2)
    config = PDFParsingConfig(layout_detection_dpi=200)

    layout = OpenCVLayoutDetector(config).detect(page, 1)
    table_regions = [region for region in layout.regions if region.type is LayoutRegionType.TABLE]
    assert table_regions

    ocr = CellOCR()
    table = OpenCVTableStructureRecognizer(config, ocr).recognize(
        page,
        1,
        table_regions[0].bbox,
    )
    document.close()

    assert table.row_count == 2
    assert table.column_count == 2
    assert ocr.calls == 4
    assert "cell-1" in table.markdown
    assert "cell-4" in table.markdown
