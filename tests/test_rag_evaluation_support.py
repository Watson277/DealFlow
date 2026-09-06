import json
from pathlib import Path

import pytest

from app.rag.evaluate_cli import _requested_modes
from app.rag.evaluation_corpus import load_corpus_manifest
from app.rag.evaluation_report import write_evaluation_report


def test_requested_modes_include_cross_encoder() -> None:
    assert _requested_modes("both") == ("dense", "hybrid")
    assert _requested_modes("all") == ("dense", "hybrid", "hybrid_reranker")
    assert _requested_modes("hybrid-reranker") == ("hybrid_reranker",)


def test_corpus_manifest_resolves_relative_files(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge.md"
    knowledge.write_text("# Knowledge", encoding="utf-8")
    manifest = tmp_path / "corpus.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "document_key": "guide-v1",
                        "path": "knowledge.md",
                        "title": "Guide",
                        "category": "Security",
                        "version": "1.0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    documents = load_corpus_manifest(manifest)

    assert documents[0].path == knowledge.resolve()
    assert documents[0].category == "security"


def test_corpus_manifest_rejects_missing_files(tmp_path: Path) -> None:
    manifest = tmp_path / "corpus.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "document_key": "missing",
                        "path": "missing.md",
                        "title": "Guide",
                        "category": "security",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not exist"):
        load_corpus_manifest(manifest)


def test_detailed_report_writes_json_jsonl_and_html(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "dataset": "dataset.jsonl",
        "corpus_manifest": "corpus.json",
        "collection": "dealflow_rag_eval_test",
        "embedding_model": "embedding-3",
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "top_k": 5,
        "candidate_k": 30,
        "reports": {
            "hybrid_reranker": {
                "hit_rate": 1.0,
                "mean_recall": 1.0,
                "mean_reciprocal_rank": 1.0,
                "mean_ndcg": 1.0,
                "mean_latency_ms": 12.5,
                "p95_latency_ms": 12.5,
                "queries": (
                    {
                        "query_id": "query-1",
                        "query": "Support <SAML>?",
                        "hit": True,
                        "reciprocal_rank": 1.0,
                        "recall": 1.0,
                        "normalized_discounted_cumulative_gain": 1.0,
                        "elapsed_ms": 12.5,
                        "candidates": (
                            {
                                "rank": 1,
                                "relevant": True,
                                "relevance": 3,
                                "title": "Guide",
                                "section_path": ["Identity"],
                                "retrieval_score": 0.9,
                                "rerank_score": 0.8,
                                "matched_child_preview": "SAML <2.0>",
                                "text_preview": "Parent",
                            },
                        ),
                    },
                ),
            }
        },
    }

    artifacts = write_evaluation_report(payload, tmp_path)

    assert Path(artifacts["summary"]).is_file()
    assert '"mode": "hybrid_reranker"' in Path(artifacts["details"]).read_text(
        encoding="utf-8"
    )
    rendered_html = Path(artifacts["html"]).read_text(encoding="utf-8")
    assert "Support &lt;SAML&gt;?" in rendered_html
    assert "SAML &lt;2.0&gt;" in rendered_html
