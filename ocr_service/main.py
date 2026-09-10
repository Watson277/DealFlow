from __future__ import annotations

import asyncio
import base64
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import cv2
import numpy as np
import numpy.typing as npt
from fastapi import FastAPI, HTTPException
from paddleocr import PaddleOCR
from pydantic import BaseModel, Field


class OCRRequest(BaseModel):
    model: str
    images: list[str] = Field(min_length=1, max_length=256)


class OCRLine(BaseModel):
    text: str
    confidence: float
    bbox: list[float]


class OCRResult(BaseModel):
    lines: list[OCRLine]


class OCRResponse(BaseModel):
    model: str
    results: list[OCRResult]


_pipeline: PaddleOCR | None = None
_inference_lock = threading.Lock()
_model_name = os.getenv("PADDLE_OCR_MODEL", "PP-OCRv6_medium")

ImageArray = npt.NDArray[np.uint8]


def _create_pipeline() -> PaddleOCR:
    return PaddleOCR(
        device=os.getenv("PADDLE_OCR_DEVICE", "cpu"),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _pipeline
    _pipeline = await asyncio.to_thread(_create_pipeline)
    yield
    _pipeline = None


app = FastAPI(title="DealFlow PaddleOCR", version="1.0.0", lifespan=lifespan)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="OCR model is not loaded")
    return {"status": "ready", "model": _model_name}


@app.post("/v1/ocr", response_model=OCRResponse)
def recognize(request: OCRRequest) -> OCRResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="OCR model is not loaded")
    if request.model != _model_name:
        raise HTTPException(
            status_code=409,
            detail=f"requested model {request.model!r} does not match loaded model {_model_name!r}",
        )
    images = [_decode_image(content) for content in request.images]
    with _inference_lock:
        results = [_predict_image(_pipeline, image) for image in images]
    return OCRResponse(model=_model_name, results=results)


def _decode_image(content: str) -> ImageArray:
    try:
        encoded = base64.b64decode(content, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="image is not valid base64") from exc
    image = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="image is not a supported image format")
    return cast(ImageArray, image)


def _predict_image(
    pipeline: PaddleOCR,
    image: ImageArray,
) -> OCRResult:
    lines: list[OCRLine] = []
    for prediction in pipeline.predict(image):
        raw = prediction.json
        payload = raw() if callable(raw) else raw
        if not isinstance(payload, dict):
            continue
        result = payload.get("res", payload)
        if not isinstance(result, dict):
            continue
        texts = result.get("rec_texts", [])
        scores = result.get("rec_scores", [])
        boxes = result.get("rec_boxes", [])
        for text, score, box in zip(texts, scores, boxes, strict=False):
            normalized_box = _rectangle(box)
            if not isinstance(text, str) or not text.strip() or normalized_box is None:
                continue
            lines.append(
                OCRLine(
                    text=text.strip(),
                    confidence=max(0.0, min(1.0, float(score))),
                    bbox=normalized_box,
                )
            )
    lines.sort(key=lambda line: (line.bbox[1], line.bbox[0]))
    return OCRResult(lines=lines)


def _rectangle(value: Any) -> list[float] | None:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size != 4:
        return None
    x0, y0, x1, y1 = (float(item) for item in array)
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]
