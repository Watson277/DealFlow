"""Downloadable artifacts produced by the local PDF parsing test endpoint."""

from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.documents.parser import ParsedDocument
from app.documents.pdf.serialization import serialize_document_ir


def build_pdf_parse_bundle(parsed: ParsedDocument, source_filename: str) -> tuple[str, bytes]:
    """Return a safe ZIP filename and a self-contained PDF parsing result bundle."""

    document_ir = parsed.document_ir
    if document_ir is None:
        raise ValueError("PDF parsing did not produce a DocumentIR")

    stem = _safe_stem(source_filename)
    summary = {
        "source_filename": source_filename,
        "document_id": str(document_ir.document_id),
        "parser_version": document_ir.parser_version,
        "document_type": document_ir.document_type.value,
        "status": document_ir.status.value,
        "page_count": document_ir.page_count,
        "page_extraction": document_ir.metadata.get("page_extraction"),
        "page_types": [page.page_type.value for page in document_ir.pages],
        "page_routes": [
            {
                "page_number": page.page_number,
                "page_type": page.page_type.value,
                "route": _page_route(page.metadata.get("routing")),
                "block_count": len(page.blocks),
                "warning_count": len(page.warnings),
            }
            for page in document_ir.pages
        ],
        "warning_count": len(document_ir.warnings),
        "files": {
            "document_ir": f"{stem}.document-ir.json",
            "markdown": f"{stem}.parsed.md",
            "summary": f"{stem}.summary.json",
        },
    }

    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{stem}.document-ir.json",
            serialize_document_ir(document_ir).encode("utf-8"),
        )
        archive.writestr(
            f"{stem}.parsed.md",
            _parsed_markdown(parsed, source_filename).encode("utf-8"),
        )
        archive.writestr(
            f"{stem}.summary.json",
            (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )
    return f"{stem}.pdf-parse-result.zip", output.getvalue()


def _parsed_markdown(parsed: ParsedDocument, source_filename: str) -> str:
    document_ir = parsed.document_ir
    if document_ir is None:
        raise ValueError("PDF parsing did not produce a DocumentIR")
    return (
        f"# PDF 解析结果：{source_filename}\n\n"
        f"- Document ID：`{document_ir.document_id}`\n"
        f"- Parser：`{document_ir.parser_version}`\n"
        f"- Document Type：`{document_ir.document_type.value}`\n"
        f"- Page Count：`{document_ir.page_count}`\n\n"
        f"{parsed.text.rstrip()}\n"
    )


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip()
    normalized = re.sub(r"[^\w.-]+", "-", stem, flags=re.UNICODE).strip("-._")
    return normalized[:80] or "parsed-pdf"


def _page_route(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    route = value.get("route")
    return route if isinstance(route, str) else None
