"""Page-region detection and table recognition primitives."""

from app.documents.pdf.layout.detection import (
    LayoutDetectionResult,
    LayoutDetector,
    LayoutRegion,
    LayoutRegionType,
    OpenCVLayoutDetector,
)
from app.documents.pdf.layout.tables import NativeTableExtraction, NativeTableRegion
from app.documents.pdf.layout.tsr import (
    OpenCVTableStructureRecognizer,
    ScannedTableResult,
    TableStructureRecognizer,
)

__all__ = [
    "LayoutDetectionResult",
    "LayoutDetector",
    "LayoutRegion",
    "LayoutRegionType",
    "NativeTableExtraction",
    "NativeTableRegion",
    "OpenCVLayoutDetector",
    "OpenCVTableStructureRecognizer",
    "ScannedTableResult",
    "TableStructureRecognizer",
]
