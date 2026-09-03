from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence
from dataclasses import replace
from time import perf_counter
from typing import Any, Protocol

import structlog

from app.core.config import Settings
from app.core.exceptions import CapabilityEvaluationError
from app.rag.vector_store import RetrievedEvidence

logger = structlog.get_logger(__name__)


class EvidenceReranker(Protocol):
    async def rerank(
        self,
        query: str,
        evidence: list[RetrievedEvidence],
        *,
        limit: int,
    ) -> list[RetrievedEvidence]: ...


class RrfEvidenceReranker:
    """Keep the fused retrieval order when reranking is disabled."""

    async def rerank(
        self,
        query: str,
        evidence: list[RetrievedEvidence],
        *,
        limit: int,
    ) -> list[RetrievedEvidence]:
        del query
        return evidence[: max(limit, 0)]


class CrossEncoderEvidenceReranker:
    """Rerank retrieved Child evidence with one lazily loaded Cross Encoder."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any | None = None
        self._model_lock = threading.Lock()

    async def rerank(
        self,
        query: str,
        evidence: list[RetrievedEvidence],
        *,
        limit: int,
    ) -> list[RetrievedEvidence]:
        if not evidence or limit < 1:
            return []
        if not self.settings.capability_reranker_enabled:
            return evidence[:limit]

        started_at = perf_counter()
        try:
            reranked, batch_size = await asyncio.to_thread(
                self._rerank_sync,
                query,
                evidence,
                limit,
            )
        except Exception as exc:
            if not self.settings.capability_reranker_fallback_enabled:
                raise CapabilityEvaluationError(
                    f"Cross Encoder reranking failed: {exc}"
                ) from exc
            logger.warning(
                "capability_reranker_fell_back_to_rrf",
                error_type=type(exc).__name__,
                error=str(exc)[:500],
                candidate_count=len(evidence),
            )
            return evidence[:limit]

        logger.info(
            "capability_evidence_reranked",
            model=self.settings.capability_reranker_model,
            candidate_count=len(evidence),
            result_count=len(reranked),
            batch_size=batch_size,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return reranked

    def _rerank_sync(
        self,
        query: str,
        evidence: list[RetrievedEvidence],
        limit: int,
    ) -> tuple[list[RetrievedEvidence], int]:
        model = self._load_model()
        tokenizer = model.tokenizer
        truncated_query = self._truncate(
            tokenizer,
            query,
            self.settings.capability_reranker_query_max_tokens,
        )
        pairs = [
            (
                truncated_query,
                self._truncate(
                    tokenizer,
                    self._knowledge_text(item),
                    self.settings.capability_reranker_knowledge_max_tokens,
                ),
            )
            for item in evidence
        ]
        raw_scores, batch_size = self._predict_with_oom_retry(model, pairs)
        scores = self._scores(raw_scores)
        if len(scores) != len(evidence):
            raise RuntimeError("Cross Encoder returned an unexpected number of scores")

        ranked = sorted(
            (
                (score, original_rank, replace(item, rerank_score=score))
                for original_rank, (item, score) in enumerate(
                    zip(evidence, scores, strict=True)
                )
            ),
            key=lambda value: (-value[0], value[1]),
        )
        return [item for _, _, item in ranked[:limit]], batch_size

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model

            import torch
            from sentence_transformers import CrossEncoder

            device = self.settings.capability_reranker_device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA was requested but is not available")

            model_kwargs: dict[str, Any] = {}
            if device == "cuda":
                model_kwargs["torch_dtype"] = torch.float16
            self._model = CrossEncoder(
                self.settings.capability_reranker_model,
                device=device,
                max_length=(
                    self.settings.capability_reranker_query_max_tokens
                    + self.settings.capability_reranker_knowledge_max_tokens
                    + 8
                ),
                activation_fn=torch.nn.Sigmoid(),
                model_kwargs=model_kwargs,
            )
            return self._model

    def _predict_with_oom_retry(
        self,
        model: Any,
        pairs: Sequence[tuple[str, str]],
    ) -> tuple[Any, int]:
        batch_size = min(self.settings.capability_reranker_batch_size, len(pairs))
        while True:
            try:
                return (
                    model.predict(
                        list(pairs),
                        batch_size=batch_size,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    ),
                    batch_size,
                )
            except RuntimeError as exc:
                if "out of memory" not in str(exc).lower() or batch_size == 1:
                    raise
                next_batch_size = max(1, batch_size // 2)
                logger.warning(
                    "capability_reranker_reducing_batch_size",
                    previous_batch_size=batch_size,
                    next_batch_size=next_batch_size,
                )
                self._empty_cuda_cache()
                batch_size = next_batch_size

    @staticmethod
    def _empty_cuda_cache() -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            return

    @staticmethod
    def _truncate(tokenizer: Any, text: str, max_tokens: int) -> str:
        token_ids = tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=True,
            max_length=max_tokens,
        )
        return str(tokenizer.decode(token_ids, skip_special_tokens=True))

    @staticmethod
    def _knowledge_text(item: RetrievedEvidence) -> str:
        child_text = item.matched_child_text or item.text
        section = " > ".join(item.section_path) if item.section_path else "Unsectioned"
        return (
            f"Title: {item.title}\n"
            f"Category: {item.category}\n"
            f"Section: {section}\n"
            f"Evidence:\n{child_text}"
        )

    @staticmethod
    def _scores(raw_scores: Any) -> list[float]:
        values = raw_scores.tolist() if hasattr(raw_scores, "tolist") else raw_scores
        if not isinstance(values, list):
            values = [values]
        scores: list[float] = []
        for value in values:
            if isinstance(value, list):
                if len(value) != 1:
                    raise RuntimeError("Cross Encoder must return one score per candidate")
                value = value[0]
            scores.append(float(value))
        return scores
