import json
from io import BytesIO
from zipfile import ZipFile

import pymupdf
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _native_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((30, 60), "DealFlow local PDF parser test")
    content = document.tobytes()
    document.close()
    return content


def _client(app_env: str = "development") -> TestClient:
    settings = Settings(
        _env_file=None,
        app_env=app_env,
        pdf_ocr_enabled=False,
        pdf_vlm_enabled=False,
    )
    return TestClient(create_app(settings))


def test_pdf_test_endpoint_returns_document_ir_markdown_and_summary_zip() -> None:
    response = _client().post(
        "/dev/pdf/parse",
        files={"file": ("本地 测试.pdf", _native_pdf(), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-pdf-page-count"] == "1"
    assert response.headers["x-pdf-document-type"] == "text_based"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]

    with ZipFile(BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert names == [
            "本地-测试.document-ir.json",
            "本地-测试.parsed.md",
            "本地-测试.summary.json",
        ]
        document_ir = json.loads(archive.read(names[0]))
        markdown = archive.read(names[1]).decode("utf-8")
        summary = json.loads(archive.read(names[2]))

    assert document_ir["schema_version"] == "1.0"
    assert document_ir["page_count"] == 1
    assert "DealFlow local PDF parser test" in markdown
    assert summary["page_types"] == ["text"]
    assert summary["page_extraction"]["mode"] == "sequential"
    assert summary["page_extraction"]["fallback_reason"] == "below_minimum_pages"
    assert summary["page_routes"][0]["route"] == "native_pymupdf"


def test_pdf_test_endpoint_rejects_non_pdf_and_invalid_pdf() -> None:
    non_pdf = _client().post(
        "/dev/pdf/parse",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    invalid_pdf = _client().post(
        "/dev/pdf/parse",
        files={"file": ("broken.pdf", b"not a PDF", "application/pdf")},
    )

    assert non_pdf.status_code == 415
    assert invalid_pdf.status_code == 422
    assert invalid_pdf.json()["detail"]["code"] == "PDF_INVALID"


def test_pdf_test_endpoint_is_hidden_outside_local_environments() -> None:
    response = _client("production").post(
        "/dev/pdf/parse",
        files={"file": ("test.pdf", _native_pdf(), "application/pdf")},
    )

    assert response.status_code == 404
