"""Development-only endpoint for manually exercising the unified PDF parser."""

from __future__ import annotations

import asyncio
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status

from app.core.config import Settings
from app.core.exceptions import DocumentProcessingError
from app.documents.parser import DocumentParser
from app.documents.pdf.bundle import build_pdf_parse_bundle
from app.documents.pdf.errors import PDFPreflightError

router = APIRouter(prefix="/dev/pdf", tags=["development"])

_LOCAL_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


@router.post(
    "/parse",
    response_class=Response,
    responses={
        200: {
            "description": "ZIP containing DocumentIR JSON, parsed Markdown, and a summary",
            "content": {"application/zip": {}},
        }
    },
    summary="Parse a local PDF for testing",
)
async def parse_local_pdf(
    request: Request,
    file: Annotated[UploadFile, File(description="Local PDF file to parse")],
) -> Response:
    settings: Settings = request.app.state.settings
    if settings.app_env.casefold() not in _LOCAL_ENVIRONMENTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="only PDF files are supported by this test endpoint",
        )

    try:
        content = await file.read(settings.max_rfp_upload_size_bytes + 1)
    finally:
        await file.close()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF file is empty")
    if len(content) > settings.max_rfp_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF exceeds the {settings.max_rfp_upload_size_bytes}-byte limit",
        )

    parser = DocumentParser.from_settings(settings)
    try:
        parsed = await asyncio.to_thread(parser.parse, content, filename)
    except PDFPreflightError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code.value, "message": str(exc)},
        ) from exc
    except DocumentProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "PDF_PROCESSING_FAILED", "message": str(exc)},
        ) from exc

    download_name, bundle = build_pdf_parse_bundle(parsed, filename)
    encoded_download_name = quote(download_name, safe=".-_")
    return Response(
        content=bundle,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                "attachment; filename=pdf-parse-result.zip; "
                f"filename*=UTF-8''{encoded_download_name}"
            ),
            "X-PDF-Page-Count": str(parsed.page_count or 0),
            "X-PDF-Document-Type": (
                parsed.document_ir.document_type.value if parsed.document_ir else "unknown"
            ),
        },
    )
