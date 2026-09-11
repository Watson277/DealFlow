"""Offline contract tests, independent of cloud credentials and private PDFs."""

import json
from io import BytesIO
from zipfile import ZipFile

import httpx
import pymupdf
import pytest

from app.core.config import Settings
from app.core.exceptions import DocumentProcessingError
from app.documents.parser import DocumentParser
from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.mineru import MinerUPDFParser, convert_layout
from app.documents.pdf.models import DocumentIR
from app.documents.pdf.native import NativePDFParser


def sample():
    with pymupdf.open() as doc:
        for _ in range(2):
            doc.new_page(width=600, height=800).insert_text((30, 30), "Native page text")
        pdf = doc.tobytes()
    pages = []
    for i in range(2):
        pages.append(
            {
                "page_idx": i,
                "page_size": [300, 400],
                "preproc_blocks": [
                    {
                        "type": "table",
                        "bbox": [10, 20, 200, 200],
                        "blocks": [
                            {
                                "lines": [
                                    {
                                        "spans": [
                                            {
                                                "type": "table",
                                                "html": (
                                                    f"<table><tr><td>page{i}</td></tr>"
                                                    "<tr><td>data</td></tr></table>"
                                                ),
                                            }
                                        ]
                                    }
                                ]
                            }
                        ],
                    }
                ],
                "para_blocks": [{"text": "WRONG CROSS PAGE MERGE"}],
            }
        )
    return pdf, {"pdf_info": pages}


def test_conversion_preserves_schema_pages_tables_and_bbox():
    pdf, layout = sample()
    result = convert_layout(layout, pdf, "test.pdf")
    assert DocumentIR.model_validate_json(result.ir.model_dump_json()) == result.ir
    assert [len(p.blocks) for p in result.pages] == [1, 1]
    assert result.pages[0].blocks[0].bbox.x0 == 20
    assert result.pages[0].blocks[0].bbox.y0 == 40
    assert "page1" not in result.pages[0].blocks[0].text
    assert "WRONG" not in result.text
    assert "| --- |" in result.pages[0].blocks[0].table_markdown
    assert "<table>" in result.pages[0].blocks[0].metadata["table_html"]


@pytest.mark.parametrize("damage", ["count", "order", "missing", "bbox"])
def test_invalid_layout_rejected(damage):
    pdf, layout = sample()
    if damage == "count":
        layout["pdf_info"].pop()
    elif damage == "order":
        layout["pdf_info"].reverse()
    elif damage == "missing":
        del layout["pdf_info"][0]["preproc_blocks"]
    else:
        layout["pdf_info"][0]["preproc_blocks"][0]["bbox"][2] = 9999
    with pytest.raises(ValueError):
        convert_layout(layout, pdf, "test.pdf")


def test_backend_selection_and_missing_token():
    assert isinstance(
        DocumentParser.from_settings(Settings(_env_file=None, pdf_backend="native")).pdf_parser,
        NativePDFParser,
    )
    parser = DocumentParser.from_settings(Settings(_env_file=None, pdf_backend="mineru"))
    assert isinstance(parser.pdf_parser, MinerUPDFParser)
    with pytest.raises(DocumentProcessingError, match="MINERU_API_TOKEN"):
        parser.parse(sample()[0], "test.pdf")
    assert parser.parse(b"# Markdown", "test.md").text == "# Markdown"


def test_remote_flow_no_storage_credentials_and_artifact_retention(monkeypatch, tmp_path):
    pdf, layout = sample()
    archive = BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("layout.json", json.dumps(layout))
        zipped.writestr("images/test.jpg", b"test-image")
    client = httpx.Client

    def handler(request):
        if request.url.host == "storage.example":
            assert "authorization" not in request.headers
            return httpx.Response(200, content=archive.getvalue())
        assert request.headers["authorization"] == "Bearer private-token"
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"batch_id": "batch", "file_urls": ["https://storage.example/upload"]},
                },
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "extract_result": [
                        {"state": "done", "full_zip_url": "https://storage.example/result"}
                    ]
                },
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handler), **kw)
    )
    parser = MinerUPDFParser(
        Settings(
            _env_file=None, mineru_api_token="private-token", local_artifact_export_dir=tmp_path
        ),
        PDFParsingConfig(),
    )
    parsed = parser.parse(pdf, "test.pdf")
    assert "private-token" not in parsed.ir.model_dump_json()
    assert len(list(tmp_path.rglob("result.zip"))) == 1


def test_error_sanitized_no_fallback(monkeypatch):
    parser = MinerUPDFParser(
        Settings(_env_file=None, mineru_api_token="private-token"), PDFParsingConfig()
    )

    def fail(*args):
        raise httpx.ConnectError("secret signed URL")

    monkeypatch.setattr(parser, "_extract", fail)
    with pytest.raises(DocumentProcessingError, match="ConnectError") as error:
        parser.parse(sample()[0], "test.pdf")
    assert "secret" not in str(error.value)
