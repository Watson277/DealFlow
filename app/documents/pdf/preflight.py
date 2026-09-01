"""Fast validation performed before native page extraction."""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import PDFPreflightCode, PDFPreflightError


@dataclass(frozen=True, slots=True)
class PDFPreflightResult:
    filename: str
    file_size_bytes: int
    page_count: int
    metadata: dict[str, JsonValue]


class PDFPreflightValidator:
    def __init__(self, config: PDFParsingConfig) -> None:
        self.config = config

    def validate(
        self,
        document: pymupdf.Document,
        *,
        filename: str,
        file_size_bytes: int,
    ) -> PDFPreflightResult:
        if not document.is_pdf:
            raise PDFPreflightError(PDFPreflightCode.INVALID, "document is not a valid PDF")
        if document.needs_pass:
            raise PDFPreflightError(
                PDFPreflightCode.ENCRYPTED,
                "password-protected PDF documents are not supported",
            )
        if document.page_count < 1:
            raise PDFPreflightError(PDFPreflightCode.EMPTY, "PDF document contains no pages")
        if document.page_count > self.config.max_pages:
            raise PDFPreflightError(
                PDFPreflightCode.PAGE_LIMIT_EXCEEDED,
                f"PDF page count exceeds the configured limit of {self.config.max_pages}",
            )

        metadata: dict[str, JsonValue] = {
            str(key): value
            for key, value in (document.metadata or {}).items()
            if value is None or isinstance(value, (str, int, float, bool))
        }
        return PDFPreflightResult(
            filename=filename,
            file_size_bytes=file_size_bytes,
            page_count=document.page_count,
            metadata=metadata,
        )
