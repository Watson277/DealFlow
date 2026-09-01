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
