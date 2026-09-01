import base64
import hashlib
from uuid import UUID

import pymupdf

from app.documents.pdf import (
    DocumentIR,
    NativePDFParser,
    PDFParseStatus,
    PDFParsingConfig,
    document_ir_object_key,
    serialize_document_ir,
)

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _text_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "DealFlow requires a complete structured proposal document for deployment.",
    )
    content = document.tobytes()
    document.close()
    return content


def test_parser_builds_complete_document_ir_with_supplied_id() -> None:
    content = _text_pdf()
    document_id = UUID("4a90a0ad-3671-4f2d-a943-68716370be0a")

    parsed = NativePDFParser().parse(content, "request.pdf", document_id)

    assert parsed.ir.document_id == document_id
    assert parsed.ir.schema_version == "1.0"
    assert parsed.ir.parser_version == parsed.parser_version
    assert parsed.ir.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert parsed.ir.status is PDFParseStatus.SUCCEEDED
    assert parsed.ir.pages == parsed.pages
    assert parsed.ir.warnings == parsed.warnings
    assert parsed.ir.metadata["file_size_bytes"] == len(content)


def test_document_ir_serialization_round_trips_and_uses_common_key() -> None:
    document_id = UUID("e7a99f7c-2941-472e-91e1-a62f4399c430")
    document_ir = NativePDFParser().parse(_text_pdf(), "request.pdf", document_id).ir

    payload = serialize_document_ir(document_ir)
    restored = DocumentIR.model_validate_json(payload)

    assert payload.endswith("\n")
    assert restored == document_ir
    assert (
        document_ir_object_key(document_id)
        == "documents/e7a99f7c-2941-472e-91e1-a62f4399c430/parsed/document-ir.v1.json"
    )


def test_parser_derives_stable_id_and_marks_nonfatal_degradation_partial() -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=300)
    page.insert_image(page.rect, stream=ONE_PIXEL_PNG)
    content = document.tobytes()
    document.close()
    parser = NativePDFParser(PDFParsingConfig(ocr_enabled=False))

    first = parser.parse(content, "scan.pdf")
    second = parser.parse(content, "scan.pdf")

    assert first.ir.document_id == second.ir.document_id
    assert first.ir.status is PDFParseStatus.PARTIAL_SUCCESS
    assert first.ir.warnings[0].code == "OCR_REQUIRED"
