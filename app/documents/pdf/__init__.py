"""PDF parsing intermediate representation."""

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import (
    PDFOCRError,
    PDFOCRErrorCode,
    PDFPreflightCode,
    PDFPreflightError,
)
from app.documents.pdf.layout import PDFLayoutAnalyzer
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
from app.documents.pdf.native import NativePDFDocument, NativePDFParser
from app.documents.pdf.ocr import OCRBlock, OCRPageResult, OCRProvider, TesseractOCRProvider
from app.documents.pdf.preflight import PDFPreflightResult
from app.documents.pdf.quality import PageQuality, PageQualityDetector
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
    "DOCUMENT_IR_CONTENT_TYPE",
    "DOCUMENT_IR_FILENAME",
    "NativePDFDocument",
    "NativePDFParser",
    "OCRBlock",
    "OCRPageResult",
    "OCRProvider",
    "PDFBlockSource",
    "PDFBlockType",
    "PDFDocumentType",
    "PDFPageType",
    "PDFOCRError",
    "PDFOCRErrorCode",
    "PDFParseStatus",
    "PDFLayoutAnalyzer",
    "PDFParsingConfig",
    "PDFPreflightCode",
    "PDFPreflightError",
    "PDFPreflightResult",
    "PDFWarningSeverity",
    "PageIR",
    "PageQuality",
    "PageQualityDetector",
    "ParseWarning",
    "TesseractOCRProvider",
    "document_ir_object_key",
    "serialize_document_ir",
]
