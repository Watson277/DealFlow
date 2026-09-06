import json
import math
from pathlib import Path

import pytest

from app.rag.evaluation import evaluate_retrieval, load_evaluation_cases
from app.rag.vector_store import RetrievedEvidence


def _evidence(title: str, section: str, score: float) -> RetrievedEvidence:
    return RetrievedEvidence(
        point_id=f"{title}-{section}",
        document_id="document-1",
        title=title,
        version="1.0",
        category="test",
        page_number=None,
        text="Evidence",
        score=score,
        section_path=(section,),
    )


def test_retrieval_evaluation_computes_hit_recall_and_mrr(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "query_id": "identity",
                "query": "Support SAML",
                "category": "security",
                "relevant": [
                    {"title": "Product Guide", "section_path": ["Identity"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    cases = load_evaluation_cases(dataset)

    report = evaluate_retrieval(
        cases,
        [[_evidence("Wrong Guide", "Other", 0.9), _evidence("Product Guide", "Identity", 0.8)]],
        top_k=2,
    )

    assert report.hit_rate == 1.0
    assert report.mean_recall == 1.0
    assert report.mean_reciprocal_rank == 0.5
    assert report.mean_ndcg == pytest.approx(1 / math.log2(3))
    assert report.queries[0].first_relevant_rank == 2
    assert report.queries[0].candidates[1].relevant is True
    assert report.queries[0].candidates[1].text_preview == "Evidence"


def test_retrieval_evaluation_computes_graded_ndcg_and_latency(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "query_id": "graded",
                "query": "Identity and audit controls",
                "category": "security",
                "difficulty": "hard",
                "critical": True,
                "relevant": [
                    {
                        "title": "Guide",
                        "section_path": ["Identity"],
                        "relevance": 3,
                    },
                    {
                        "title": "Guide",
                        "section_path": ["Audit"],
                        "relevance": 1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    cases = load_evaluation_cases(dataset)

    report = evaluate_retrieval(
        cases,
        [[_evidence("Guide", "Audit", 0.9), _evidence("Guide", "Identity", 0.8)]],
        top_k=2,
        latencies_ms=[12.5],
    )

    actual_dcg = 1 + 7 / math.log2(3)
    ideal_dcg = 7 + 1 / math.log2(3)
    assert report.mean_ndcg == pytest.approx(actual_dcg / ideal_dcg)
    assert report.mean_latency_ms == 12.5
    assert report.p95_latency_ms == 12.5
    assert report.queries[0].difficulty == "hard"
    assert report.queries[0].critical is True


def test_retrieval_evaluation_counts_each_relevance_label_once_for_ndcg(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "query_id": "duplicate-parent-section",
                "query": "Identity controls",
                "category": "security",
                "relevant": [
                    {
                        "title": "Guide",
                        "section_path": ["Identity"],
                        "relevance": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cases = load_evaluation_cases(dataset)

    report = evaluate_retrieval(
        cases,
        [[_evidence("Guide", "Identity", 0.9), _evidence("Guide", "Identity", 0.8)]],
        top_k=2,
    )

    assert report.mean_ndcg == 1.0
    assert report.mean_ndcg <= 1.0
    assert report.mean_recall == 1.0
    assert report.queries[0].candidates[0].relevance == 3
    assert report.queries[0].candidates[1].relevance == 3
    assert report.queries[0].candidates[1].relevant is True


def test_retrieval_evaluation_rejects_duplicate_query_ids(tmp_path: Path) -> None:
    case = {
        "query_id": "duplicate",
        "query": "Support SAML",
        "category": "security",
        "relevant": [{"title": "Guide", "section_path": ["Identity"]}],
    }
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        f"{json.dumps(case)}\n{json.dumps(case)}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="query_id values must be unique"):
        load_evaluation_cases(dataset)
