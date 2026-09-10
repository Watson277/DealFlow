"""Replaceable page OCR provider backed by the Tesseract CLI."""

from __future__ import annotations

import base64
import csv
import io
import shutil
import statistics
import subprocess
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx
import pymupdf
from pydantic import JsonValue

from app.documents.pdf.config import PDFParsingConfig
from app.documents.pdf.errors import PDFOCRError, PDFOCRErrorCode
from app.documents.pdf.models import BoundingBox


@dataclass(frozen=True, slots=True)
class OCRBlock:
    text: str
    bbox: BoundingBox
    confidence: float | None
    metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class OCRPageResult:
    blocks: tuple[OCRBlock, ...]
    provider: str
    rendered_width: int
    rendered_height: int
    dpi: int
    languages: str


class OCRProvider(Protocol):
    @property
    def name(self) -> str: ...

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult: ...

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult: ...


@dataclass(frozen=True, slots=True)
class _RenderedRegion:
    content_base64: str
    clip: pymupdf.Rect
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class _OCRWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    line_key: tuple[int, int, int, int]
    word_number: int


class TesseractOCRProvider:
    """Render a PDF page and map Tesseract TSV coordinates back to PDF points."""

    name = "tesseract"

    def __init__(self, config: PDFParsingConfig) -> None:
        self.config = config

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        return self._recognize(page, page_number, bbox=None)

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult:
        return self._recognize(page, page_number, bbox=bbox)

    def recognize_regions(
        self,
        page: pymupdf.Page,
        page_number: int,
        bboxes: Sequence[BoundingBox],
    ) -> tuple[OCRPageResult, ...]:
        return tuple(self.recognize_region(page, page_number, bbox) for bbox in bboxes)

    def _recognize(
        self,
        page: pymupdf.Page,
        page_number: int,
        *,
        bbox: BoundingBox | None,
    ) -> OCRPageResult:
        executable = shutil.which(self.config.ocr_executable)
        if executable is None:
            raise PDFOCRError(
                PDFOCRErrorCode.UNAVAILABLE,
                "Tesseract executable is not installed or not on PATH",
            )

        clip = (
            pymupdf.Rect(  # type: ignore[no-untyped-call]
                bbox.x0, bbox.y0, bbox.x1, bbox.y1
            )
            if bbox is not None
            else page.rect
        )
        pixmap = page.get_pixmap(
            dpi=self.config.ocr_dpi,
            colorspace=pymupdf.csRGB,
            alpha=False,
            clip=clip,
        )
        image = pixmap.tobytes("png")  # type: ignore[no-untyped-call]
        command = [
            executable,
            "stdin",
            "stdout",
            "-l",
            self.config.ocr_languages,
            "--psm",
            str(self.config.ocr_page_segmentation_mode),
            "tsv",
        ]
        try:
            completed = subprocess.run(
                command,
                input=image,
                capture_output=True,
                check=False,
                timeout=self.config.ocr_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise PDFOCRError(
                PDFOCRErrorCode.TIMEOUT,
                f"Tesseract exceeded the {self.config.ocr_timeout_seconds:g}s page timeout",
            ) from exc
        except OSError as exc:
            raise PDFOCRError(
                PDFOCRErrorCode.UNAVAILABLE,
                "Tesseract could not be started",
            ) from exc

        if completed.returncode != 0:
            raise PDFOCRError(
                PDFOCRErrorCode.FAILED,
                f"Tesseract exited with status {completed.returncode}",
            )

        try:
            words = _parse_tsv(completed.stdout.decode("utf-8", errors="replace"))
        except (KeyError, TypeError, ValueError, csv.Error) as exc:
            raise PDFOCRError(
                PDFOCRErrorCode.INVALID_OUTPUT,
                "Tesseract returned malformed TSV output",
            ) from exc

        blocks = _line_blocks(
            words,
            region_width=float(clip.width),
            region_height=float(clip.height),
            origin_x=float(clip.x0),
            origin_y=float(clip.y0),
            page_width=float(page.rect.width),
            page_height=float(page.rect.height),
            image_width=pixmap.width,
            image_height=pixmap.height,
            provider=self.name,
            languages=self.config.ocr_languages,
            dpi=self.config.ocr_dpi,
        )
        return OCRPageResult(
            blocks=blocks,
            provider=self.name,
            rendered_width=pixmap.width,
            rendered_height=pixmap.height,
            dpi=self.config.ocr_dpi,
            languages=self.config.ocr_languages,
        )


class PaddleOCRHTTPProvider:
    """Call a shared PaddleOCR service while preserving PDF-space coordinates."""

    name = "paddleocr"

    def __init__(self, config: PDFParsingConfig) -> None:
        self.config = config

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        return self.recognize_regions(
            page,
            page_number,
            (BoundingBox(x0=0.0, y0=0.0, x1=float(page.rect.width), y1=float(page.rect.height)),),
        )[0]

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult:
        return self.recognize_regions(page, page_number, (bbox,))[0]

    def recognize_regions(
        self,
        page: pymupdf.Page,
        page_number: int,
        bboxes: Sequence[BoundingBox],
    ) -> tuple[OCRPageResult, ...]:
        if not bboxes:
            return ()
        rendered = tuple(self._render_region(page, bbox) for bbox in bboxes)
        outputs: list[OCRPageResult] = []
        batch_size = self.config.paddle_ocr_batch_size
        for start in range(0, len(rendered), batch_size):
            batch = rendered[start : start + batch_size]
            payload = self._request_batch(batch)
            outputs.extend(
                self._to_page_result(
                    item,
                    region,
                    page_number=page_number,
                    batch_index=start + index,
                    page_width=float(page.rect.width),
                    page_height=float(page.rect.height),
                )
                for index, (item, region) in enumerate(zip(payload, batch, strict=True))
            )
        return tuple(outputs)

    def _render_region(
        self,
        page: pymupdf.Page,
        bbox: BoundingBox,
    ) -> _RenderedRegion:
        clip = pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)  # type: ignore[no-untyped-call]
        pixmap = page.get_pixmap(
            dpi=self.config.ocr_dpi,
            colorspace=pymupdf.csRGB,
            alpha=False,
            clip=clip,
        )
        content = base64.b64encode(pixmap.tobytes("png")).decode("ascii")  # type: ignore[no-untyped-call]
        return _RenderedRegion(
            content_base64=content,
            clip=clip,
            width=pixmap.width,
            height=pixmap.height,
        )

    def _request_batch(self, regions: Sequence[_RenderedRegion]) -> list[dict[str, Any]]:
        request = {
            "model": self.config.paddle_ocr_model,
            "images": [region.content_base64 for region in regions],
        }
        try:
            with httpx.Client(timeout=self.config.paddle_ocr_timeout_seconds) as client:
                response = client.post(self.config.paddle_ocr_url, json=request)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise PDFOCRError(
                PDFOCRErrorCode.TIMEOUT,
                "PaddleOCR service request timed out",
            ) from exc
        except httpx.HTTPError as exc:
            raise PDFOCRError(
                PDFOCRErrorCode.UNAVAILABLE,
                "PaddleOCR service is unavailable",
            ) from exc

        try:
            body = cast(dict[str, Any], response.json())
            results = body["results"]
            if not isinstance(results, list) or len(results) != len(regions):
                raise ValueError("result count does not match request count")
            if not all(isinstance(result, dict) for result in results):
                raise TypeError("result items must be objects")
            return cast(list[dict[str, Any]], results)
        except (KeyError, TypeError, ValueError) as exc:
            raise PDFOCRError(
                PDFOCRErrorCode.INVALID_OUTPUT,
                "PaddleOCR service returned malformed JSON",
            ) from exc

    def _to_page_result(
        self,
        payload: dict[str, Any],
        region: _RenderedRegion,
        *,
        page_number: int,
        batch_index: int,
        page_width: float,
        page_height: float,
    ) -> OCRPageResult:
        lines = payload.get("lines")
        if not isinstance(lines, list):
            raise PDFOCRError(
                PDFOCRErrorCode.INVALID_OUTPUT,
                "PaddleOCR result is missing lines",
            )
        blocks: list[OCRBlock] = []
        for line_number, item in enumerate(lines, 1):
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            score = item.get("confidence")
            bbox = item.get("bbox")
            if not isinstance(text, str) or not text.strip():
                continue
            if (
                not isinstance(bbox, list)
                or len(bbox) != 4
                or not all(isinstance(value, (int, float)) for value in bbox)
            ):
                continue
            x0, y0, x1, y1 = (float(value) for value in bbox)
            mapped = _map_pixel_bbox_to_page(
                x0,
                y0,
                x1,
                y1,
                region=region,
                page_width=page_width,
                page_height=page_height,
            )
            if mapped is None:
                continue
            confidence = (
                max(0.0, min(1.0, float(score)))
                if isinstance(score, (int, float))
                else None
            )
            blocks.append(
                OCRBlock(
                    text=unicodedata.normalize("NFKC", text.strip()),
                    bbox=mapped,
                    confidence=confidence,
                    metadata={
                        "ocr_provider": self.name,
                        "ocr_model": self.config.paddle_ocr_model,
                        "ocr_page_number": page_number,
                        "ocr_batch_index": batch_index,
                        "ocr_line": line_number,
                    },
                )
            )
        blocks.sort(key=lambda block: (block.bbox.y0, block.bbox.x0))
        return OCRPageResult(
            blocks=tuple(blocks),
            provider=self.name,
            rendered_width=region.width,
            rendered_height=region.height,
            dpi=self.config.ocr_dpi,
            languages="zh+en",
        )


class FallbackOCRProvider:
    """Use the secondary provider when the primary provider fails or returns no text."""

    def __init__(self, primary: OCRProvider, fallback: OCRProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}+{fallback.name}-fallback"

    def recognize_page(self, page: pymupdf.Page, page_number: int) -> OCRPageResult:
        return self._recognize_with_fallback(
            lambda: self.primary.recognize_page(page, page_number),
            lambda: self.fallback.recognize_page(page, page_number),
        )

    def recognize_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> OCRPageResult:
        return self._recognize_with_fallback(
            lambda: self.primary.recognize_region(page, page_number, bbox),
            lambda: self.fallback.recognize_region(page, page_number, bbox),
        )

    def recognize_regions(
        self,
        page: pymupdf.Page,
        page_number: int,
        bboxes: Sequence[BoundingBox],
    ) -> tuple[OCRPageResult, ...]:
        primary_batch = getattr(self.primary, "recognize_regions", None)
        fallback_batch = getattr(self.fallback, "recognize_regions", None)
        try:
            primary_results = (
                tuple(primary_batch(page, page_number, bboxes))
                if callable(primary_batch)
                else tuple(
                    self.primary.recognize_region(page, page_number, bbox) for bbox in bboxes
                )
            )
        except PDFOCRError:
            return (
                tuple(fallback_batch(page, page_number, bboxes))
                if callable(fallback_batch)
                else tuple(
                    self.fallback.recognize_region(page, page_number, bbox) for bbox in bboxes
                )
            )

        resolved = list(primary_results)
        for index, result in enumerate(primary_results):
            if result.blocks:
                continue
            resolved[index] = self.fallback.recognize_region(
                page,
                page_number,
                bboxes[index],
            )
        return tuple(resolved)

    @staticmethod
    def _recognize_with_fallback(
        primary: Any,
        fallback: Any,
    ) -> OCRPageResult:
        try:
            result = cast(OCRPageResult, primary())
        except PDFOCRError:
            return cast(OCRPageResult, fallback())
        return result if result.blocks else cast(OCRPageResult, fallback())


def create_ocr_provider(config: PDFParsingConfig) -> OCRProvider:
    tesseract = TesseractOCRProvider(config)
    if config.ocr_provider == "tesseract":
        return tesseract
    paddle = PaddleOCRHTTPProvider(config)
    if config.ocr_fallback_enabled:
        return FallbackOCRProvider(paddle, tesseract)
    return paddle


def _map_pixel_bbox_to_page(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    region: _RenderedRegion,
    page_width: float,
    page_height: float,
) -> BoundingBox | None:
    if region.width <= 0 or region.height <= 0:
        return None
    bounded_x0 = max(0.0, min(float(region.width), x0))
    bounded_y0 = max(0.0, min(float(region.height), y0))
    bounded_x1 = max(0.0, min(float(region.width), x1))
    bounded_y1 = max(0.0, min(float(region.height), y1))
    if bounded_x1 <= bounded_x0 or bounded_y1 <= bounded_y0:
        return None
    scale_x = float(region.clip.width) / region.width
    scale_y = float(region.clip.height) / region.height
    return BoundingBox(
        x0=max(0.0, min(page_width, float(region.clip.x0) + bounded_x0 * scale_x)),
        y0=max(0.0, min(page_height, float(region.clip.y0) + bounded_y0 * scale_y)),
        x1=max(0.0, min(page_width, float(region.clip.x0) + bounded_x1 * scale_x)),
        y1=max(0.0, min(page_height, float(region.clip.y0) + bounded_y1 * scale_y)),
    )


def _parse_tsv(content: str) -> tuple[_OCRWord, ...]:
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    required = {
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("missing Tesseract TSV columns")

    words: list[_OCRWord] = []
    for row in reader:
        text = row["text"].strip()
        if row["level"] != "5" or not text:
            continue
        confidence = float(row["conf"])
        if confidence < 0:
            continue
        width = int(row["width"])
        height = int(row["height"])
        if width <= 0 or height <= 0:
            continue
        words.append(
            _OCRWord(
                text=text,
                left=int(row["left"]),
                top=int(row["top"]),
                width=width,
                height=height,
                confidence=max(0.0, min(1.0, confidence / 100.0)),
                line_key=(
                    int(row["page_num"]),
                    int(row["block_num"]),
                    int(row["par_num"]),
                    int(row["line_num"]),
                ),
                word_number=int(row["word_num"]),
            )
        )
    return tuple(words)


def _line_blocks(
    words: Sequence[_OCRWord],
    *,
    region_width: float,
    region_height: float,
    origin_x: float,
    origin_y: float,
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
    provider: str,
    languages: str,
    dpi: int,
) -> tuple[OCRBlock, ...]:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("rendered OCR image has invalid dimensions")
    grouped: dict[tuple[int, int, int, int], list[_OCRWord]] = defaultdict(list)
    for word in words:
        grouped[word.line_key].append(word)

    scale_x = region_width / image_width
    scale_y = region_height / image_height
    blocks: list[OCRBlock] = []
    for line_key, line_words in grouped.items():
        line_words.sort(key=lambda word: (word.word_number, word.left))
        segments = _split_line_at_large_gaps(line_words, image_width)
        for segment_number, segment_words in enumerate(segments, start=1):
            text = _join_words([word.text for word in segment_words])
            if not text:
                continue
            left = min(word.left for word in segment_words)
            top = min(word.top for word in segment_words)
            right = max(word.left + word.width for word in segment_words)
            bottom = max(word.top + word.height for word in segment_words)
            bbox = BoundingBox(
                x0=max(0.0, min(page_width, origin_x + left * scale_x)),
                y0=max(0.0, min(page_height, origin_y + top * scale_y)),
                x1=max(0.0, min(page_width, origin_x + right * scale_x)),
                y1=max(0.0, min(page_height, origin_y + bottom * scale_y)),
            )
            confidence = sum(word.confidence for word in segment_words) / len(segment_words)
            blocks.append(
                OCRBlock(
                    text=text,
                    bbox=bbox,
                    confidence=round(confidence, 6),
                    metadata={
                        "ocr_provider": provider,
                        "ocr_languages": languages,
                        "ocr_dpi": dpi,
                        "ocr_line": list(line_key),
                        "ocr_line_segment": segment_number,
                        "ocr_word_count": len(segment_words),
                    },
                )
            )
    blocks.sort(key=lambda block: (block.bbox.y0, block.bbox.x0))
    return tuple(blocks)


def _split_line_at_large_gaps(
    words: Sequence[_OCRWord],
    image_width: int,
) -> tuple[tuple[_OCRWord, ...], ...]:
    if len(words) < 2:
        return (tuple(words),)
    typical_height = statistics.median(word.height for word in words)
    gap_threshold = max(typical_height * 3.0, image_width * 0.04)
    segments: list[list[_OCRWord]] = [[words[0]]]
    for previous, current in zip(words, words[1:], strict=False):
        gap = current.left - (previous.left + previous.width)
        if gap > gap_threshold:
            segments.append([])
        segments[-1].append(current)
    return tuple(tuple(segment) for segment in segments if segment)


def _join_words(words: Sequence[str]) -> str:
    result = ""
    closing_punctuation = set(",.!?;:%)]}，。！？；：、）】》」』”’")
    opening_punctuation = set("([{（【《「『“‘")
    for word in words:
        if not result:
            result = word
            continue
        previous = result[-1]
        current = word[0]
        needs_space = not (
            _is_cjk(previous)
            or _is_cjk(current)
            or current in closing_punctuation
            or previous in opening_punctuation
        )
        result += (" " if needs_space else "") + word
    return result.strip()


def _is_cjk(character: str) -> bool:
    name = unicodedata.name(character, "")
    return "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name or "HANGUL" in name
