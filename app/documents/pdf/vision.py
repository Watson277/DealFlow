"""Optional OpenAI-compatible VLM provider for detected image regions."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

import pymupdf
from openai import OpenAI
from pydantic import JsonValue

from app.core.config import Settings
from app.documents.pdf.errors import PDFVisionError
from app.documents.pdf.models import BoundingBox


@dataclass(frozen=True, slots=True)
class VisionRegionResult:
    caption: str | None
    visible_text: str | None
    provider: str
    model: str
    metadata: dict[str, JsonValue]


class VisionProvider(Protocol):
    @property
    def name(self) -> str: ...

    def analyze_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> VisionRegionResult: ...


class DisabledVisionProvider:
    name = "disabled"

    def analyze_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> VisionRegionResult:
        raise PDFVisionError("VLM image-region analysis is disabled")


class OpenAICompatibleVisionProvider:
    name = "openai-compatible-vlm"

    def __init__(self, settings: Settings) -> None:
        api_key = settings.pdf_vlm_api_key or settings.llm_api_key
        model = (settings.pdf_vlm_model or "").strip()
        if api_key is None or not model:
            raise ValueError("PDF_VLM_ENABLED requires PDF_VLM_MODEL and a VLM/LLM API key")
        self.model = model
        self.max_tokens = settings.pdf_vlm_max_tokens
        self.client = OpenAI(
            api_key=api_key.get_secret_value(),
            base_url=settings.pdf_vlm_base_url or settings.llm_base_url,
            timeout=settings.pdf_vlm_timeout_seconds,
            max_retries=1,
        )

    def analyze_region(
        self,
        page: pymupdf.Page,
        page_number: int,
        bbox: BoundingBox,
    ) -> VisionRegionResult:
        clip = pymupdf.Rect(  # type: ignore[no-untyped-call]
            bbox.x0, bbox.y0, bbox.x1, bbox.y1
        )
        pixmap = page.get_pixmap(dpi=180, colorspace=pymupdf.csRGB, alpha=False, clip=clip)
        encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")  # type: ignore[no-untyped-call]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=cast(
                    Any,
                    [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Analyze this PDF image region. Return one JSON object "
                                        "with caption and visible_text string fields. Keep the "
                                        "caption concise, preserve facts, and use an empty "
                                        "string when no visible text exists."
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{encoded}",
                                    },
                                },
                            ],
                        }
                    ],
                ),
                max_tokens=self.max_tokens,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise PDFVisionError("VLM request failed for an image region") from exc
        if not response.choices or response.choices[0].message.content is None:
            raise PDFVisionError("VLM returned no image-region result")
        content = response.choices[0].message.content
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PDFVisionError("VLM image-region result is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise PDFVisionError("VLM image-region result must be a JSON object")
        caption = _optional_text(payload.get("caption"))
        visible_text = _optional_text(payload.get("visible_text"))
        return VisionRegionResult(
            caption=caption,
            visible_text=visible_text,
            provider=self.name,
            model=self.model,
            metadata={
                "page_number": page_number,
                "rendered_width": pixmap.width,
                "rendered_height": pixmap.height,
            },
        )


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None
