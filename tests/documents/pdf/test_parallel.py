from collections.abc import Callable
from concurrent.futures import Executor, Future
from typing import Any, TypeVar

import pymupdf

from app.documents.pdf import NativePDFParser, PDFParsingConfig, TesseractOCRProvider
from app.documents.pdf.native import _page_batches

T = TypeVar("T")


def _multipage_pdf(page_count: int) -> bytes:
    document = pymupdf.open()
    for page_number in range(1, page_count + 1):
        page = document.new_page(width=300, height=400)
        page.insert_text(
            (30, 100),
            f"Unique requirement content for page {page_number}",
        )
    content = document.tobytes()
    document.close()
    return content


class ReverseResultExecutor(Executor):
    def __init__(self) -> None:
        self.batches: list[tuple[int, ...]] = []

    def submit(
        self,
        fn: Callable[..., T],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[T]:
        self.batches.append(args[1])
        future: Future[T] = Future()
        result = fn(*args, **kwargs)
        if isinstance(result, tuple):
            result = tuple(reversed(result))
        future.set_result(result)
        return future


class FailingExecutor(Executor):
    def submit(
        self,
        fn: Callable[..., T],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[T]:
        future: Future[T] = Future()
        future.set_exception(RuntimeError("simulated process-pool failure"))
        return future


def test_page_batches_are_distributed_round_robin() -> None:
    assert _page_batches(10, 4) == (
        (1, 5, 9),
        (2, 6, 10),
        (3, 7),
        (4, 8),
    )


def test_parallel_page_results_are_returned_in_page_number_order() -> None:
    executor = ReverseResultExecutor()
    content = _multipage_pdf(6)
    config = PDFParsingConfig(
        ocr_enabled=False,
        page_parallel_enabled=True,
        page_workers=2,
        page_parallel_min_pages=2,
    )

    parsed = NativePDFParser(config, page_executor=executor).parse(content, "parallel.pdf")
    sequential = NativePDFParser(
        PDFParsingConfig(ocr_enabled=False, page_parallel_enabled=False)
    ).parse(content, "parallel.pdf")

    assert executor.batches == [(1, 3, 5), (2, 4, 6)]
    assert [page.page_number for page in parsed.pages] == [1, 2, 3, 4, 5, 6]
    assert [f"page {number}" in parsed.text for number in range(1, 7)] == [True] * 6
    assert parsed.pages == sequential.pages
    assert parsed.text == sequential.text
    assert parsed.ir.metadata["page_extraction"] == {
        "requested": True,
        "applied": True,
        "mode": "process_pool",
        "configured_workers": 2,
        "worker_count": 2,
        "minimum_pages": 2,
        "batch_count": 2,
        "fallback_reason": None,
        "output_order": "page_number_ascending",
    }


def test_parallel_failure_falls_back_to_sequential_extraction() -> None:
    config = PDFParsingConfig(
        ocr_enabled=False,
        page_parallel_enabled=True,
        page_workers=2,
        page_parallel_min_pages=2,
    )

    parsed = NativePDFParser(config, page_executor=FailingExecutor()).parse(
        _multipage_pdf(3),
        "fallback.pdf",
    )

    execution = parsed.ir.metadata["page_extraction"]
    assert execution["applied"] is False
    assert execution["mode"] == "sequential_fallback"
    assert execution["fallback_reason"] == "parallel_error:RuntimeError"
    assert [page.page_number for page in parsed.pages] == [1, 2, 3]


def test_custom_provider_disables_process_pool_for_safe_fallback() -> None:
    config = PDFParsingConfig(
        ocr_enabled=False,
        page_parallel_enabled=True,
        page_workers=2,
        page_parallel_min_pages=2,
    )
    executor = FailingExecutor()

    parsed = NativePDFParser(
        config,
        ocr_provider=TesseractOCRProvider(config),
        page_executor=executor,
    ).parse(_multipage_pdf(3), "custom-provider.pdf")

    execution = parsed.ir.metadata["page_extraction"]
    assert execution["applied"] is False
    assert execution["mode"] == "sequential"
    assert execution["fallback_reason"] == "custom_or_vlm_provider"


def test_real_process_pool_extracts_pages_and_preserves_order() -> None:
    config = PDFParsingConfig(
        ocr_enabled=False,
        page_parallel_enabled=True,
        page_workers=2,
        page_parallel_min_pages=2,
    )

    parsed = NativePDFParser(config).parse(_multipage_pdf(4), "real-process-pool.pdf")

    execution = parsed.ir.metadata["page_extraction"]
    assert execution["applied"] is True
    assert execution["mode"] == "process_pool"
    assert execution["worker_count"] == 2
    assert [page.page_number for page in parsed.pages] == [1, 2, 3, 4]
