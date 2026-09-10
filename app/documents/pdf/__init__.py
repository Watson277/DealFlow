"""PDF parsing intermediate representation."""

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import (
    PDFOCRError,
    PDFOCRErrorCode,
    PDFPreflightCode,
    PDFPreflightError,
    PDFTableRecognitionError,
    PDFVisionError,
)
from app.documents.pdf.fusion import BlockFusion, BlockFusionResult
from app.documents.pdf.layout import (
    LayoutDetectionResult,
    LayoutDetector,
    LayoutRegion,
    LayoutRegionType,
    OpenCVLayoutDetector,
    OpenCVTableStructureRecognizer,
    ScannedTableResult,
    TableStructureRecognizer,
)
from app.documents.pdf.layout.analyzer import PDFLayoutAnalyzer
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
from app.documents.pdf.ocr import (
    FallbackOCRProvider,
    OCRBlock,
    OCRPageResult,
    OCRProvider,
    PaddleOCRHTTPProvider,
    TesseractOCRProvider,
    create_ocr_provider,
)
from app.documents.pdf.preflight import PDFPreflightResult
from app.documents.pdf.quality import PageQuality, PageQualityDetector
from app.documents.pdf.serialization import (
    DOCUMENT_IR_CONTENT_TYPE,
    DOCUMENT_IR_FILENAME,
    document_ir_object_key,
    serialize_document_ir,
)
from app.documents.pdf.vision import (
    DisabledVisionProvider,
    OpenAICompatibleVisionProvider,
    VisionProvider,
    VisionRegionResult,
)

__all__ = [
    "BlockIR",
    "BlockFusion",
    "BlockFusionResult",
    "BoundingBox",
    "DocumentIR",
    "DOCUMENT_IR_CONTENT_TYPE",
    "DOCUMENT_IR_FILENAME",
    "NativePDFDocument",
    "NativePDFParser",
    "LayoutDetectionResult",
    "LayoutDetector",
    "LayoutRegion",
    "LayoutRegionType",
    "OCRBlock",
    "OCRPageResult",
    "OCRProvider",
    "PaddleOCRHTTPProvider",
    "PDFBlockSource",
    "PDFBlockType",
    "PDFDocumentType",
    "PDFPageType",
    "PDFOCRError",
    "PDFOCRErrorCode",
    "PDFTableRecognitionError",
    "PDFVisionError",
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
    "OpenCVLayoutDetector",
    "OpenCVTableStructureRecognizer",
    "OpenAICompatibleVisionProvider",
    "DisabledVisionProvider",
    "ScannedTableResult",
    "TableStructureRecognizer",
    "TesseractOCRProvider",
    "FallbackOCRProvider",
    "VisionProvider",
    "VisionRegionResult",
    "document_ir_object_key",
    "create_ocr_provider",
    "serialize_document_ir",
]
