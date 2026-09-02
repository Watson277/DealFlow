import json
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
    assert report.queries[0].first_relevant_rank == 2


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
