from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from app.rag.vector_store import RetrievedEvidence


@dataclass(frozen=True, slots=True)
class RelevanceLabel:
    title: str
    section_path: tuple[str, ...]
    relevance: int = 1


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationCase:
    query_id: str
    query: str
    category: str
    relevant: tuple[RelevanceLabel, ...]
    difficulty: str | None = None
    critical: bool = False


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    rank: int
    point_id: str
    document_id: str
    parent_id: str | None
    chunk_id: str | None
    title: str
    section_path: tuple[str, ...]
    retrieval_score: float
    rerank_score: float | None
    relevance: int
    relevant: bool
    text_preview: str
    matched_child_preview: str | None


@dataclass(frozen=True, slots=True)
class QueryEvaluation:
    query_id: str
    query: str
    category: str
    difficulty: str | None
    critical: bool
    hit: bool
    reciprocal_rank: float
    recall: float
    normalized_discounted_cumulative_gain: float
    first_relevant_rank: int | None
    elapsed_ms: float | None
    candidates: tuple[CandidateEvaluation, ...]


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationReport:
    query_count: int
    top_k: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_recall: float
    mean_ndcg: float
    mean_latency_ms: float | None
    p95_latency_ms: float | None
    queries: tuple[QueryEvaluation, ...]


def load_evaluation_cases(path: Path) -> list[RetrievalEvaluationCase]:
    cases: list[RetrievalEvaluationCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            relevant = tuple(
                RelevanceLabel(
                    title=str(item["title"]),
                    section_path=tuple(str(value) for value in item["section_path"]),
                    relevance=int(item.get("relevance", 1)),
                )
                for item in payload["relevant"]
            )
            case = RetrievalEvaluationCase(
                query_id=str(payload["query_id"]),
                query=str(payload["query"]),
                category=str(payload["category"]),
                relevant=relevant,
                difficulty=(
                    str(payload["difficulty"]) if payload.get("difficulty") is not None else None
                ),
                critical=bool(payload.get("critical", False)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid retrieval evaluation case at line {line_number}") from exc
        if not case.query_id or not case.query or not case.relevant:
            raise ValueError(f"empty retrieval evaluation field at line {line_number}")
        if any(label.relevance < 1 for label in case.relevant):
            raise ValueError(f"relevance must be positive at line {line_number}")
        cases.append(case)
    if not cases:
        raise ValueError("retrieval evaluation dataset is empty")
    if len({case.query_id for case in cases}) != len(cases):
        raise ValueError("retrieval evaluation query_id values must be unique")
    return cases


def evaluate_retrieval(
    cases: list[RetrievalEvaluationCase],
    results: list[list[RetrievedEvidence]],
    *,
    top_k: int,
    latencies_ms: list[float] | None = None,
) -> RetrievalEvaluationReport:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if len(cases) != len(results):
        raise ValueError("evaluation cases and retrieval results do not align")
    if latencies_ms is not None and len(latencies_ms) != len(cases):
        raise ValueError("evaluation cases and latency results do not align")

    query_reports: list[QueryEvaluation] = []
    for case_index, (case, candidates) in enumerate(zip(cases, results, strict=True)):
        ranked = candidates[:top_k]
        matched_labels: set[int] = set()
        first_relevant_rank: int | None = None
        discounted_cumulative_gain = 0.0
        candidate_reports: list[CandidateEvaluation] = []
        for rank, candidate in enumerate(ranked, start=1):
            candidate_label_indexes = {
                label_index
                for label_index, label in enumerate(case.relevant)
                if _matches(candidate, label)
            }
            candidate_relevance = max(
                (
                    case.relevant[label_index].relevance
                    for label_index in candidate_label_indexes
                ),
                default=0,
            )
            novel_relevance = max(
                (
                    case.relevant[label_index].relevance
                    for label_index in candidate_label_indexes - matched_labels
                ),
                default=0,
            )
            if candidate_label_indexes and first_relevant_rank is None:
                first_relevant_rank = rank
            matched_labels.update(candidate_label_indexes)
            if novel_relevance:
                discounted_cumulative_gain += _discounted_gain(novel_relevance, rank)
            candidate_reports.append(
                CandidateEvaluation(
                    rank=rank,
                    point_id=candidate.point_id,
                    document_id=candidate.document_id,
                    parent_id=candidate.parent_id,
                    chunk_id=candidate.chunk_id,
                    title=candidate.title,
                    section_path=candidate.section_path,
                    retrieval_score=candidate.score,
                    rerank_score=candidate.rerank_score,
                    relevance=candidate_relevance,
                    relevant=candidate_relevance > 0,
                    text_preview=_preview(candidate.text),
                    matched_child_preview=(
                        _preview(candidate.matched_child_text)
                        if candidate.matched_child_text is not None
                        else None
                    ),
                )
            )
        reciprocal_rank = (
            1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
        )
        ideal_relevances = sorted(
            (label.relevance for label in case.relevant), reverse=True
        )[:top_k]
        ideal_discounted_cumulative_gain = sum(
            _discounted_gain(relevance, rank)
            for rank, relevance in enumerate(ideal_relevances, start=1)
        )
        ndcg = (
            discounted_cumulative_gain / ideal_discounted_cumulative_gain
            if ideal_discounted_cumulative_gain
            else 0.0
        )
        query_reports.append(
            QueryEvaluation(
                query_id=case.query_id,
                query=case.query,
                category=case.category,
                difficulty=case.difficulty,
                critical=case.critical,
                hit=first_relevant_rank is not None,
                reciprocal_rank=reciprocal_rank,
                recall=len(matched_labels) / len(case.relevant),
                normalized_discounted_cumulative_gain=ndcg,
                first_relevant_rank=first_relevant_rank,
                elapsed_ms=(latencies_ms[case_index] if latencies_ms is not None else None),
                candidates=tuple(candidate_reports),
            )
        )

    count = len(query_reports)
    measured_latencies = [
        item.elapsed_ms for item in query_reports if item.elapsed_ms is not None
    ]
    return RetrievalEvaluationReport(
        query_count=count,
        top_k=top_k,
        hit_rate=sum(item.hit for item in query_reports) / count,
        mean_reciprocal_rank=sum(item.reciprocal_rank for item in query_reports) / count,
        mean_recall=sum(item.recall for item in query_reports) / count,
        mean_ndcg=sum(
            item.normalized_discounted_cumulative_gain for item in query_reports
        )
        / count,
        mean_latency_ms=(
            sum(measured_latencies) / len(measured_latencies) if measured_latencies else None
        ),
        p95_latency_ms=_percentile(measured_latencies, 0.95),
        queries=tuple(query_reports),
    )


def _matches(candidate: RetrievedEvidence, label: RelevanceLabel) -> bool:
    if candidate.title.casefold() != label.title.casefold():
        return False
    return candidate.section_path[: len(label.section_path)] == label.section_path


def _discounted_gain(relevance: int, rank: int) -> float:
    return float((2**relevance - 1) / math.log2(rank + 1))


def _preview(text: str, limit: int = 500) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]
