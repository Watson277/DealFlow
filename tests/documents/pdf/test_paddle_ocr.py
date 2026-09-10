from __future__ import annotations

from typing import Any

import pymupdf
import pytest

from app.documents.pdf import (
    BoundingBox,
    FallbackOCRProvider,
    OCRBlock,
    OCRPageResult,
    PaddleOCRHTTPProvider,
    PDFOCRError,
    PDFOCRErrorCode,
    PDFParsingConfig,
    TesseractOCRProvider,
    create_ocr_provider,
)
from app.documents.pdf import ocr as ocr_module


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, _: str, *, json: dict[str, Any]) -> _FakeResponse:
        self.requests.append(json)
        return self.response


def test_paddle_provider_batches_regions_and_maps_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(
        {
            "model": "PP-OCRv6_medium",
            "results": [
                {
                    "lines": [
                        {
                            "text": "审计日志",
                            "confidence": 0.97,
                            "bbox": [10, 20, 110, 60],
                        }
                    ]
                },
                {"lines": []},
            ],
        }
    )
    client = _FakeClient(response)
    monkeypatch.setattr(ocr_module.httpx, "Client", lambda **_: client)
    document = pymupdf.open()
    page = document.new_page(width=200, height=300)
    bboxes = (
        BoundingBox(x0=20, y0=30, x1=180, y1=100),
        BoundingBox(x0=20, y0=120, x1=180, y1=200),
    )
    config = PDFParsingConfig(
        ocr_provider="paddleocr",
        ocr_dpi=200,
        paddle_ocr_url="http://ocr.test/v1/ocr",
        paddle_ocr_batch_size=8,
    )

    results = PaddleOCRHTTPProvider(config).recognize_regions(page, 1, bboxes)

    document.close()
    assert len(client.requests) == 1
    assert len(client.requests[0]["images"]) == 2
    assert len(results) == 2
    assert results[0].blocks[0].text == "审计日志"
    assert results[0].blocks[0].confidence == pytest.approx(0.97)
    assert bboxes[0].x0 <= results[0].blocks[0].bbox.x0 < results[0].blocks[0].bbox.x1
    assert results[0].blocks[0].bbox.x1 <= bboxes[0].x1
    assert results[1].blocks == ()


class _UnavailableProvider:
    name = "unavailable"

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        raise PDFOCRError(PDFOCRErrorCode.UNAVAILABLE, "unavailable")

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult:
        raise PDFOCRError(PDFOCRErrorCode.UNAVAILABLE, "unavailable")


class _SuccessfulProvider:
    name = "fallback"

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        return self.recognize_region(
            page,
            page_number,
            BoundingBox(x0=0, y0=0, x1=float(page.rect.width), y1=float(page.rect.height)),
        )

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult:
        return OCRPageResult(
            blocks=(
                OCRBlock(
                    text="fallback text",
                    bbox=bbox,
                    confidence=0.8,
                    metadata={},
                ),
            ),
            provider=self.name,
            rendered_width=100,
            rendered_height=50,
            dpi=250,
            languages="eng",
        )


def test_fallback_provider_uses_tesseract_compatible_secondary_on_failure() -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=300)
    provider = FallbackOCRProvider(_UnavailableProvider(), _SuccessfulProvider())

    result = provider.recognize_page(page, 1)

    document.close()
    assert result.provider == "fallback"
    assert result.blocks[0].text == "fallback text"


def test_ocr_provider_factory_keeps_tesseract_as_configurable_fallback() -> None:
    paddle = create_ocr_provider(
        PDFParsingConfig(ocr_provider="paddleocr", ocr_fallback_enabled=True)
    )
    tesseract = create_ocr_provider(PDFParsingConfig(ocr_provider="tesseract"))

    assert isinstance(paddle, FallbackOCRProvider)
    assert isinstance(tesseract, TesseractOCRProvider)
