"""Replaceable page OCR provider backed by the Tesseract CLI."""

from __future__ import annotations

import csv
import io
import shutil
import statistics
import subprocess
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

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
        executable = shutil.which(self.config.ocr_executable)
        if executable is None:
            raise PDFOCRError(
                PDFOCRErrorCode.UNAVAILABLE,
                "Tesseract executable is not installed or not on PATH",
            )

        pixmap = page.get_pixmap(
            dpi=self.config.ocr_dpi,
            colorspace=pymupdf.csRGB,
            alpha=False,
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

    scale_x = page_width / image_width
    scale_y = page_height / image_height
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
                x0=max(0.0, min(page_width, left * scale_x)),
                y0=max(0.0, min(page_height, top * scale_y)),
                x1=max(0.0, min(page_width, right * scale_x)),
                y1=max(0.0, min(page_height, bottom * scale_y)),
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
