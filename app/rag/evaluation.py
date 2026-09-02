from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.rag.vector_store import RetrievedEvidence


@dataclass(frozen=True, slots=True)
class RelevanceLabel:
    title: str
    section_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationCase:
    query_id: str
    query: str
    category: str
    relevant: tuple[RelevanceLabel, ...]


@dataclass(frozen=True, slots=True)
class QueryEvaluation:
    query_id: str
    hit: bool
    reciprocal_rank: float
    recall: float
    first_relevant_rank: int | None


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationReport:
    query_count: int
    top_k: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_recall: float
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
                )
                for item in payload["relevant"]
            )
            case = RetrievalEvaluationCase(
                query_id=str(payload["query_id"]),
                query=str(payload["query"]),
                category=str(payload["category"]),
                relevant=relevant,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid retrieval evaluation case at line {line_number}") from exc
        if not case.query_id or not case.query or not case.relevant:
            raise ValueError(f"empty retrieval evaluation field at line {line_number}")
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
) -> RetrievalEvaluationReport:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if len(cases) != len(results):
        raise ValueError("evaluation cases and retrieval results do not align")

    query_reports: list[QueryEvaluation] = []
    for case, candidates in zip(cases, results, strict=True):
        ranked = candidates[:top_k]
        matched_labels: set[int] = set()
        first_relevant_rank: int | None = None
        for rank, candidate in enumerate(ranked, start=1):
            for label_index, label in enumerate(case.relevant):
                if _matches(candidate, label):
                    matched_labels.add(label_index)
                    if first_relevant_rank is None:
                        first_relevant_rank = rank
        reciprocal_rank = (
            1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
        )
        query_reports.append(
            QueryEvaluation(
                query_id=case.query_id,
                hit=first_relevant_rank is not None,
                reciprocal_rank=reciprocal_rank,
                recall=len(matched_labels) / len(case.relevant),
                first_relevant_rank=first_relevant_rank,
            )
        )

    count = len(query_reports)
    return RetrievalEvaluationReport(
        query_count=count,
        top_k=top_k,
        hit_rate=sum(item.hit for item in query_reports) / count,
        mean_reciprocal_rank=sum(item.reciprocal_rank for item in query_reports) / count,
        mean_recall=sum(item.recall for item in query_reports) / count,
        queries=tuple(query_reports),
    )


def _matches(candidate: RetrievedEvidence, label: RelevanceLabel) -> bool:
    if candidate.title.casefold() != label.title.casefold():
        return False
    return candidate.section_path[: len(label.section_path)] == label.section_path
