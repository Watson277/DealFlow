import pymupdf

from app.documents.pdf import (
    BlockIR,
    BoundingBox,
    NativePDFParser,
    PageIR,
    PDFBlockSource,
    PDFBlockType,
    PDFLayoutAnalyzer,
    PDFPageType,
    PDFParsingConfig,
)


def text_block(
    block_id: str,
    text: str,
    bbox: tuple[float, float, float, float],
    *,
    order: int,
    font_size: float = 12,
    source: PDFBlockSource = PDFBlockSource.NATIVE,
) -> BlockIR:
    return BlockIR(
        block_id=block_id,
        type=PDFBlockType.TEXT,
        bbox=BoundingBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
        source=source,
        reading_order=order,
        text=text,
        raw_text=text,
        metadata={"font_sizes": [font_size]},
    )


def page(page_number: int, blocks: list[BlockIR]) -> PageIR:
    return PageIR(
        page_number=page_number,
        width=600,
        height=800,
        page_type=PDFPageType.TEXT,
        blocks=tuple(blocks),
    )


def test_layout_restores_two_column_reading_order_and_merges_ocr_lines() -> None:
    pages: list[PageIR] = []
    for page_number in range(1, 4):
        blocks = [
            text_block(
                f"p{page_number}_header",
                "DealFlow Confidential 2026",
                (180, 20, 420, 35),
                order=0,
                font_size=8,
            ),
            text_block(
                f"p{page_number}_title",
                "1.1 Architecture Overview",
                (140, 105, 460, 135),
                order=1,
                font_size=24,
            ),
            text_block(
                f"p{page_number}_left1",
                "Left column begins",
                (40, 170, 250, 185),
                order=2,
                source=PDFBlockSource.OCR,
            ),
            text_block(
                f"p{page_number}_left2",
                "and continues here",
                (40, 195, 250, 210),
                order=3,
                source=PDFBlockSource.OCR,
            ),
            text_block(
                f"p{page_number}_right1",
                "Right column first.",
                (350, 170, 560, 185),
                order=4,
            ),
            text_block(
                f"p{page_number}_right2",
                "Right column second.",
                (350, 210, 560, 225),
                order=5,
            ),
            text_block(
                f"p{page_number}_footer",
                f"Page {page_number} / 3",
                (260, 770, 340, 785),
                order=6,
                font_size=8,
            ),
        ]
        pages.append(page(page_number, blocks))

    analyzed = PDFLayoutAnalyzer(PDFParsingConfig()).analyze(tuple(pages))

    first = analyzed[0]
    assert first.metadata["layout"]["column_count"] == 2
    assert [block.reading_order for block in first.blocks] == list(range(len(first.blocks)))
    assert first.blocks[0].type is PDFBlockType.HEADER
    assert first.blocks[-1].type is PDFBlockType.FOOTER
    title = next(block for block in first.blocks if block.type is PDFBlockType.TITLE)
    assert title.metadata["heading_level"] == 2
    visible_text = [
        block.text
        for block in first.blocks
        if block.type not in {PDFBlockType.HEADER, PDFBlockType.FOOTER}
    ]
    assert visible_text == [
        "1.1 Architecture Overview",
        "Left column begins and continues here",
        "Right column first.",
        "Right column second.",
    ]
    merged = next(block for block in first.blocks if block.text and block.text.startswith("Left"))
    assert merged.metadata["merged_block_count"] == 2
    assert merged.metadata["column_index"] == 0
    assert (
        next(block for block in first.blocks if block.text == "Right column first.").metadata[
            "column_index"
        ]
        == 1
    )


def test_layout_classifies_lists_and_removes_duplicate_overlay_text() -> None:
    duplicate = text_block("p1_duplicate", "Repeated text", (40, 100, 180, 120), order=1)
    analyzed = PDFLayoutAnalyzer(PDFParsingConfig()).analyze(
        (
            page(
                1,
                [
                    text_block("p1_text", "Repeated text", (40, 100, 180, 120), order=0),
                    duplicate.model_copy(update={"source": PDFBlockSource.OCR, "confidence": 0.8}),
                    text_block("p1_list", "- Support audit logs", (40, 160, 220, 180), order=2),
                ],
            ),
        )
    )[0]

    assert analyzed.metadata["layout"]["duplicate_blocks_removed"] == 1
    assert len([block for block in analyzed.blocks if block.text == "Repeated text"]) == 1
    assert (
        next(block for block in analyzed.blocks if block.text == "- Support audit logs").type
        is PDFBlockType.LIST
    )


def test_native_table_becomes_markdown_and_links_its_caption() -> None:
    document = pymupdf.open()
    pdf_page = document.new_page(width=400, height=300)
    xs = [40, 180, 340]
    ys = [80, 120, 160]
    for x in xs:
        pdf_page.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:
        pdf_page.draw_line((xs[0], y), (xs[-1], y))
    pdf_page.insert_text((40, 65), "Table 1 Performance metrics")
    pdf_page.insert_text((50, 105), "Metric")
    pdf_page.insert_text((190, 105), "Value")
    pdf_page.insert_text((50, 145), "Latency")
    pdf_page.insert_text((190, 145), "2 sec")
    content = document.tobytes()
    document.close()

    parsed = NativePDFParser().parse(content, "table.pdf")

    result_page = parsed.pages[0]
    tables = [block for block in result_page.blocks if block.type is PDFBlockType.TABLE]
    assert len(tables) == 1
    assert tables[0].table_markdown == ("| Metric | Value |\n| --- | --- |\n| Latency | 2 sec |")
    assert result_page.metadata["table_detection"]["table_count"] == 1
    caption = next(block for block in result_page.blocks if block.type is PDFBlockType.CAPTION)
    assert caption.metadata["caption_for_block_id"] == tables[0].block_id
    assert parsed.text.count("Metric") == 1
    assert "| Latency | 2 sec |" in parsed.text


def test_native_parser_applies_column_order_to_compatible_plain_text() -> None:
    document = pymupdf.open()
    pdf_page = document.new_page(width=600, height=500)
    pdf_page.insert_text((170, 55), "Two-column requirements", fontsize=20)
    pdf_page.insert_text((40, 130), "Left requirement one.", fontsize=11)
    pdf_page.insert_text((40, 180), "Left requirement two.", fontsize=11)
    pdf_page.insert_text((350, 130), "Right evidence one.", fontsize=11)
    pdf_page.insert_text((350, 180), "Right evidence two.", fontsize=11)
    content = document.tobytes()
    document.close()

    parsed = NativePDFParser().parse(content, "columns.pdf")

    result_page = parsed.pages[0]
    assert result_page.metadata["layout"]["column_count"] == 2
    assert parsed.text.index("Left requirement two.") < parsed.text.index("Right evidence one.")
    assert (
        next(block for block in result_page.blocks if block.text == "Two-column requirements").type
        is PDFBlockType.TITLE
    )
