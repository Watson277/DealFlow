from uuid import UUID

import pytest
from pydantic import ValidationError

from app.documents.pdf import (
    BlockIR,
    BoundingBox,
    DocumentIR,
    PageIR,
    ParseWarning,
    PDFBlockSource,
    PDFBlockType,
    PDFDocumentType,
    PDFPageType,
    PDFParseStatus,
)

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
CHECKSUM = "a" * 64


def text_block(**overrides: object) -> BlockIR:
    values: dict[str, object] = {
        "block_id": "p1_b1",
        "type": PDFBlockType.TEXT,
        "bbox": BoundingBox(x0=10, y0=20, x1=200, y1=60),
        "source": PDFBlockSource.NATIVE,
        "reading_order": 0,
        "text": "Deployment must support audit logging.",
    }
    values.update(overrides)
    return BlockIR.model_validate(values)


def page(**overrides: object) -> PageIR:
    values: dict[str, object] = {
        "page_number": 1,
        "width": 595,
        "height": 842,
        "page_type": PDFPageType.TEXT,
        "confidence": 0.98,
        "blocks": [text_block()],
    }
    values.update(overrides)
    return PageIR.model_validate(values)


def document(**overrides: object) -> DocumentIR:
    values: dict[str, object] = {
        "parser_version": "0.1.0",
        "document_id": DOCUMENT_ID,
        "source_filename": "request.pdf",
        "checksum_sha256": CHECKSUM,
        "document_type": PDFDocumentType.TEXT_BASED,
        "page_count": 1,
        "pages": [page()],
    }
    values.update(overrides)
    return DocumentIR.model_validate(values)


def test_document_ir_round_trips_as_versioned_json() -> None:
    parsed = document(
        status=PDFParseStatus.PARTIAL_SUCCESS,
        warnings=[ParseWarning(code="OCR_PAGE_FAILED", message="OCR fallback was unavailable")],
        metadata={"producer": "dealflow"},
    )

    restored = DocumentIR.model_validate_json(parsed.model_dump_json())

    assert restored == parsed
    assert restored.schema_version == "1.0"
    assert restored.pages[0].blocks[0].bbox.x1 == 200
    assert restored.model_dump(mode="json")["document_type"] == "text_based"


@pytest.mark.parametrize(
    ("coordinates", "message"),
    [
        ({"x0": 20, "y0": 0, "x1": 10, "y1": 10}, "x1 must be"),
        ({"x0": 0, "y0": 20, "x1": 10, "y1": 10}, "y1 must be"),
        ({"x0": -1, "y0": 0, "x1": 10, "y1": 10}, "greater than or equal"),
    ],
)
def test_bounding_box_rejects_invalid_coordinates(
    coordinates: dict[str, int], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        BoundingBox.model_validate(coordinates)


def test_block_rejects_invalid_content_for_its_type() -> None:
    with pytest.raises(ValidationError, match="text blocks require text"):
        text_block(text=None)

    with pytest.raises(ValidationError, match="table_markdown is only valid"):
        text_block(table_markdown="| Header |")

    with pytest.raises(ValidationError, match="less than or equal to 1"):
        text_block(confidence=1.1)


def test_page_rejects_duplicate_or_out_of_bounds_blocks() -> None:
    with pytest.raises(ValidationError, match="block_id values must be unique"):
        page(blocks=[text_block(), text_block(reading_order=1)])

    with pytest.raises(ValidationError, match="reading_order values must be unique"):
        page(blocks=[text_block(), text_block(block_id="p1_b2")])

    with pytest.raises(ValidationError, match="bbox exceeds page bounds"):
        page(blocks=[text_block(bbox=BoundingBox(x0=10, y0=20, x1=600, y1=60))])


def test_page_warning_must_reference_its_page_and_known_block() -> None:
    with pytest.raises(ValidationError, match="containing page"):
        page(warnings=[ParseWarning(code="OCR_LOW_CONFIDENCE", message="Low", page_number=2)])

    with pytest.raises(ValidationError, match="unknown block"):
        page(
            warnings=[
                ParseWarning(
                    code="OCR_LOW_CONFIDENCE",
                    message="Low",
                    page_number=1,
                    block_id="missing",
                )
            ]
        )


def test_document_requires_all_pages_in_contiguous_order() -> None:
    second_page = page(page_number=2, blocks=[text_block(block_id="p2_b1")])

    with pytest.raises(ValidationError, match="page_count must equal"):
        document(page_count=2, pages=[page()])

    with pytest.raises(ValidationError, match="ordered and numbered contiguously"):
        document(page_count=2, pages=[second_page, page()])

    with pytest.raises(ValidationError, match="block_id values must be unique within a document"):
        document(page_count=2, pages=[page(), page(page_number=2)])


def test_document_rejects_unknown_fields_and_invalid_warning_references() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        document(unknown=True)

    with pytest.raises(ValidationError, match="outside the document"):
        document(warnings=[ParseWarning(code="PAGE_FAILED", message="Failed", page_number=2)])

    with pytest.raises(ValidationError, match="unknown block"):
        document(warnings=[ParseWarning(code="BLOCK_FAILED", message="Failed", block_id="missing")])

    with pytest.raises(ValidationError, match="does not belong"):
        document(
            page_count=2,
            pages=[page(), page(page_number=2, blocks=[text_block(block_id="p2_b1")])],
            warnings=[
                ParseWarning(code="BLOCK_FAILED", message="Failed", page_number=2, block_id="p1_b1")
            ],
        )

    with pytest.raises(ValidationError, match="Input should be '1.0'"):
        document(schema_version="2.0")
