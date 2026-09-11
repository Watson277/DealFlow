"""Shared DocumentIR contracts and persistence helpers."""

from app.documents.pdf.models import (
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
    PDFWarningSeverity,
)
from app.documents.pdf.serialization import (
    DOCUMENT_IR_CONTENT_TYPE,
    DOCUMENT_IR_FILENAME,
    document_ir_object_key,
    serialize_document_ir,
)

__all__ = [
    "BlockIR",
    "BoundingBox",
    "DocumentIR",
    "PageIR",
    "ParseWarning",
    "PDFBlockSource",
    "PDFBlockType",
    "PDFDocumentType",
    "PDFPageType",
    "PDFParseStatus",
    "PDFWarningSeverity",
    "DOCUMENT_IR_CONTENT_TYPE",
    "DOCUMENT_IR_FILENAME",
    "document_ir_object_key",
    "serialize_document_ir",
]
