"""Optional remote MinerU backend; preserve page boundaries and the existing IR schema."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from uuid import UUID, uuid4
from zipfile import ZipFile

import httpx
import pymupdf

from app.core.config import Settings
from app.core.exceptions import DocumentProcessingError
from app.documents.pdf.config import PDFParsingConfig
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
)
from app.documents.pdf.native import NativePDFDocument
from app.documents.pdf.preflight import PDFPreflightValidator
from app.documents.pdf.quality import PageQualityDetector

API = "https://mineru.net/api/v4"
MAX_ARCHIVE_BYTES = 256 * 1024**2


class _TableText(HTMLParser):
    """Readable rows for retrieval; original HTML retains merged-cell semantics."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.rows = []
        self.cell = None
        self.complex = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        if tag in {"td", "th"}:
            self.cell = []
            self.complex |= any(k in {"rowspan", "colspan"} and v != "1" for k, v in attrs)

    def handle_data(self, data):
        self.parts.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"}:
            self.parts.append("\t")
            if self.rows and self.cell is not None:
                self.rows[-1].append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr":
            self.parts.append("\n")

    def markdown(self, html):
        # Complex HTML is valid embedded Markdown; never flatten merged-cell geometry.
        if self.complex or not self.rows:
            return html
        width = max(map(len, self.rows))
        if not width:
            return html
        lines = [
            "| "
            + " | ".join(
                cell.replace("|", "\\|").replace("\n", " ")
                for cell in row + [""] * (width - len(row))
            )
            + " |"
            for row in self.rows
        ]
        lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
        return "\n".join(lines)


def _spans(block):
    for line in block.get("lines", []):
        yield from line.get("spans", [])
    for child in block.get("blocks", []):
        yield from _spans(child)


def _block_text(block):
    lines = [
        "".join(str(s.get("content", "")) for s in line.get("spans", []))
        for line in block.get("lines", [])
    ]
    lines.extend(_block_text(child) for child in block.get("blocks", []))
    return "\n".join(line for line in lines if line)


def convert_layout(
    layout: dict,
    content: bytes,
    filename: str,
    document_id: UUID | str | None = None,
    config: PDFParsingConfig | None = None,
) -> NativePDFDocument:
    """Convert preproc_blocks only; never consume MinerU's cross-page para_blocks."""
    config = config or PDFParsingConfig()
    pages = []
    warnings = []
    with pymupdf.open(stream=content, filetype="pdf") as source:
        preflight = PDFPreflightValidator(config).validate(
            source, filename=filename, file_size_bytes=len(content)
        )
        remote_pages = layout.get("pdf_info", [])
        if len(remote_pages) != source.page_count:
            raise ValueError("MinerU page count does not match source PDF")
        for index, remote in enumerate(remote_pages):
            if remote.get("page_idx") != index or "preproc_blocks" not in remote:
                raise ValueError("MinerU page order or preproc_blocks is missing")
            page = source[index]
            width, height = page.rect.width, page.rect.height
            rw, rh = remote["page_size"]
            if rw <= 0 or rh <= 0:
                raise ValueError("Invalid MinerU page dimensions")
            native_blocks = page.get_text("blocks")
            quality = PageQualityDetector(config).assess(
                text=page.get_text(),
                page_width=width,
                page_height=height,
                text_bboxes=[tuple(b[:4]) for b in native_blocks if b[6] == 0],
                image_bboxes=[tuple(i["bbox"]) for i in page.get_image_info()],
            )
            blocks = []
            page_warnings = []
            # Discarded headers/footers are retained, not silently lost.
            raw_blocks = remote["preproc_blocks"] + remote.get("discarded_blocks", [])
            for order, raw in enumerate(raw_blocks):
                kind = raw.get("type", "unknown")
                mapping = {
                    "title": "title",
                    "text": "text",
                    "list": "list",
                    "table": "table",
                    "image": "image",
                    "interline_equation": "formula",
                    "header": "header",
                    "footer": "footer",
                    "page_number": "footer",
                    "table_caption": "caption",
                    "image_caption": "caption",
                    "table_footnote": "footnote",
                    "footnote": "footnote",
                }
                spans = list(_spans(raw))
                html = "\n".join(s["html"] for s in spans if s.get("html"))
                text = _block_text(raw)
                table_markdown = None
                if html:
                    reader = _TableText()
                    reader.feed(html)
                    text = "\n".join(filter(None, ["".join(reader.parts).strip(), text]))
                    table_markdown = reader.markdown(html)
                mapped = mapping.get(kind, "text")
                block_id = f"p{index + 1}-mineru-{order}"
                if kind not in mapping or (
                    not text and mapped not in {"table", "image", "formula"}
                ):
                    page_warnings.append(
                        ParseWarning(
                            code="MINERU_UNMAPPED_BLOCK",
                            page_number=index + 1,
                            message=f"Unmapped or empty MinerU block: {kind}",
                            details={"raw_block": raw},
                        )
                    )
                    if not text:
                        continue
                x0, y0, x1, y1 = raw["bbox"]
                # layout coordinates are page units, not content_list's 0..1000 scale.
                bbox = BoundingBox(
                    x0=x0 / rw * width, y0=y0 / rh * height, x1=x1 / rw * width, y1=y1 / rh * height
                )
                blocks.append(
                    BlockIR(
                        block_id=block_id,
                        type=PDFBlockType(mapped),
                        bbox=bbox,
                        source=PDFBlockSource.DERIVED,
                        reading_order=order,
                        text=text.strip() or None,
                        raw_text=text or None,
                        table_markdown=table_markdown if mapped == "table" else None,
                        latex=text.strip() or None if mapped == "formula" else None,
                        metadata={
                            "provider": "mineru",
                            "raw_block": raw,
                            "table_html": html or None,
                            "image_paths": [s["image_path"] for s in spans if s.get("image_path")],
                        },
                    )
                )
            if not blocks and quality.page_type != PDFPageType.EMPTY:
                page_warnings.append(
                    ParseWarning(
                        code="MINERU_EMPTY_PAGE",
                        page_number=index + 1,
                        message="MinerU returned no usable blocks",
                    )
                )
            warnings.extend(page_warnings)
            pages.append(
                PageIR(
                    page_number=index + 1,
                    width=width,
                    height=height,
                    page_type=quality.page_type,
                    blocks=tuple(blocks),
                    warnings=tuple(page_warnings),
                    metadata={
                        "routing": {"route": "mineru_preproc_blocks"},
                        "quality": quality.as_metadata(),
                    },
                )
            )
    types = {p.page_type for p in pages} - {PDFPageType.EMPTY}
    doc_type = (
        PDFDocumentType.TEXT_BASED
        if types <= {PDFPageType.TEXT}
        else PDFDocumentType.SCANNED
        if types == {PDFPageType.SCANNED}
        else PDFDocumentType.MIXED
    )
    ir = DocumentIR(
        document_id=UUID(str(document_id)) if document_id else uuid4(),
        source_filename=filename,
        checksum_sha256=sha256(content).hexdigest(),
        parser_version="mineru-preproc-1.0",
        document_type=doc_type,
        status=PDFParseStatus.PARTIAL_SUCCESS if warnings else PDFParseStatus.SUCCEEDED,
        page_count=len(pages),
        pages=tuple(pages),
        warnings=tuple(warnings),
        metadata={
            "provider": "mineru",
            "provider_version": layout.get("_version_name"),
            "cross_page_merge": False,
        },
    )
    text = "\n\n".join(
        b.table_markdown or b.text for p in pages for b in p.blocks if b.table_markdown or b.text
    )
    return NativePDFDocument(
        text=text,
        page_count=len(pages),
        document_type=doc_type,
        pages=tuple(pages),
        warnings=tuple(warnings),
        preflight=preflight,
        parser_version=ir.parser_version,
        ir=ir,
    )


class MinerUPDFParser:
    def __init__(self, settings: Settings, config: PDFParsingConfig):
        self.settings = settings
        self.config = config

    def parse(self, content: bytes, filename: str, document_id=None) -> NativePDFDocument:
        token = self.settings.mineru_api_token.get_secret_value().strip()
        if not token:
            raise DocumentProcessingError("MINERU_API_TOKEN is required for PDF_BACKEND=mineru")
        if len(content) > 200 * 1024**2:
            raise DocumentProcessingError("MinerU PDF exceeds 200 MiB")
        with pymupdf.open(stream=content, filetype="pdf") as source:
            PDFPreflightValidator(self.config).validate(
                source, filename=filename, file_size_bytes=len(content)
            )
        try:
            layout, archive = self._extract(content, filename, token)
            parsed = convert_layout(layout, content, filename, document_id, self.config)
            # Persist raw images and layout together; metadata paths refer to this ZIP,
            # not to temporary files or unauthenticated public URLs.
            folder = (
                self.settings.local_artifact_export_dir
                / "mineru"
                / str(parsed.ir.document_id)
                / uuid4().hex
            )
            folder.mkdir(parents=True, exist_ok=False)
            path = folder / "result.zip"
            path.write_bytes(archive)
            ir = parsed.ir.model_copy(
                update={
                    "metadata": {
                        **parsed.ir.metadata,
                        "local_artifact_archive": str(path),
                        "asset_reference_scope": "mineru_result_zip",
                    }
                }
            )
            return replace(parsed, ir=ir)
        except Exception as exc:
            # HTTP exceptions may contain signed URLs; never expose them to worker logs.
            raise DocumentProcessingError(
                f"MinerU parsing failed ({type(exc).__name__}); no native fallback"
            ) from None

    def _extract(self, content, filename, token):
        with (
            httpx.Client(timeout=60, follow_redirects=False) as api,
            httpx.Client(timeout=120, follow_redirects=False) as storage,
        ):

            def call(method, path, **kwargs):
                response = api.request(
                    method, API + path, headers={"Authorization": f"Bearer {token}"}, **kwargs
                )
                response.raise_for_status()
                body = response.json()
                if body.get("code") != 0:
                    raise ValueError("MinerU rejected request")
                return body["data"]

            data = call(
                "POST",
                "/file-urls/batch",
                json={
                    "files": [{"name": filename}],
                    "model_version": self.settings.mineru_model,
                    "enable_table": True,
                    "enable_formula": True,
                    "language": "ch",
                },
            )
            upload_url = data["file_urls"][0]
            if httpx.URL(upload_url).scheme != "https":
                raise ValueError("MinerU storage URL must use HTTPS")
            storage.put(upload_url, content=content).raise_for_status()
            deadline = time.monotonic() + self.settings.mineru_wait_seconds
            while time.monotonic() < deadline:
                result = call("GET", f"/extract-results/batch/{data['batch_id']}")
                records = result.get("extract_result", [])
                if len(records) > 1:
                    raise ValueError("Unexpected MinerU batch size")
                record = records[0] if records else {}
                if record.get("state") == "failed":
                    raise ValueError("Remote extraction failed")
                if record.get("state") == "done":
                    break
                time.sleep(min(5, max(0, deadline - time.monotonic())))
            else:
                raise TimeoutError("MinerU extraction timed out")
            url = record["full_zip_url"]
            if httpx.URL(url).scheme != "https":
                raise ValueError("MinerU result URL must use HTTPS")
            archive = BytesIO()
            with storage.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    if archive.tell() + len(chunk) > MAX_ARCHIVE_BYTES:
                        raise ValueError("MinerU archive exceeds limit")
                    archive.write(chunk)
            with ZipFile(archive) as zipped:
                layouts = [m for m in zipped.infolist() if m.filename == "layout.json"]
                if len(layouts) != 1 or layouts[0].file_size > 64 * 1024**2:
                    raise ValueError("Missing or oversized MinerU layout.json")
                return json.loads(zipped.read(layouts[0])), archive.getvalue()
