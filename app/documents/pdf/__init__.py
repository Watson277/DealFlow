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

__all__ = [
    "BlockIR",
    "BoundingBox",
    "DocumentIR",
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
]
