from app.documents.pdf import (
    BlockFusion,
    BlockIR,
    BoundingBox,
    PDFBlockSource,
    PDFBlockType,
    PDFParsingConfig,
)


def _text_block(
    block_id: str,
    source: PDFBlockSource,
    bbox: BoundingBox,
    text: str,
) -> BlockIR:
    return BlockIR(
        block_id=block_id,
        type=PDFBlockType.TEXT,
        bbox=bbox,
        source=source,
        reading_order=int(block_id[-1]),
        text=text,
    )


def test_fusion_prefers_native_text_over_matching_ocr() -> None:
    bbox = BoundingBox(x0=20, y0=30, x1=180, y1=60)
    native = _text_block("block1", PDFBlockSource.NATIVE, bbox, "Audit logs required")
    ocr = _text_block(
        "block2",
        PDFBlockSource.OCR,
        BoundingBox(x0=21, y0=30, x1=181, y1=61),
        "Audit logs required",
    )

    result = BlockFusion(PDFParsingConfig()).fuse([ocr, native])

    assert result.duplicate_blocks_removed == 1
    assert result.conflicts_resolved == 1
    assert result.blocks[0].source is PDFBlockSource.NATIVE
    assert result.blocks[0].metadata["fusion_discarded_block_ids"] == ["block2"]


def test_fusion_removes_plain_text_inside_structured_table() -> None:
    table_bbox = BoundingBox(x0=20, y0=100, x1=380, y1=220)
    table = BlockIR(
        block_id="table1",
        type=PDFBlockType.TABLE,
        bbox=table_bbox,
        source=PDFBlockSource.DERIVED,
        reading_order=0,
        table_markdown="| A | B |\n| --- | --- |\n| 1 | 2 |",
    )
    text = _text_block(
        "block1",
        PDFBlockSource.OCR,
        BoundingBox(x0=30, y0=120, x1=200, y1=145),
        "A B 1 2",
    )

    result = BlockFusion(PDFParsingConfig()).fuse([text, table])

    assert result.table_text_blocks_removed == 1
    assert result.blocks == (table,)
