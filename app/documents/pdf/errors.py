"""Stable error codes raised during PDF preflight."""

from enum import StrEnum

from app.core.exceptions import DocumentProcessingError


class PDFPreflightCode(StrEnum):
    INVALID = "PDF_INVALID"
    ENCRYPTED = "PDF_ENCRYPTED"
    EMPTY = "PDF_EMPTY"
    PAGE_LIMIT_EXCEEDED = "PDF_PAGE_LIMIT_EXCEEDED"


class PDFPreflightError(DocumentProcessingError):
    def __init__(self, code: PDFPreflightCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class PDFOCRErrorCode(StrEnum):
    UNAVAILABLE = "PDF_OCR_UNAVAILABLE"
    TIMEOUT = "PDF_OCR_TIMEOUT"
    FAILED = "PDF_OCR_FAILED"
    INVALID_OUTPUT = "PDF_OCR_INVALID_OUTPUT"


class PDFOCRError(DocumentProcessingError):
    def __init__(self, code: PDFOCRErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
