from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.rag.embedding import OpenAIEmbeddingService
from app.rag.evaluation import evaluate_retrieval, load_evaluation_cases
from app.rag.retrieval import expand_parent_evidence
from app.rag.vector_store import QdrantKnowledgeStore

EvaluationMode = Literal["dense", "hybrid"]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate DealFlow knowledge retrieval")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/retrieval/sample_queries.jsonl"),
    )
    parser.add_argument("--mode", choices=("dense", "hybrid", "both"), default="both")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def _evaluate(args: argparse.Namespace) -> dict[str, object]:
    cases = load_evaluation_cases(args.dataset)
    settings = get_settings()
    embeddings = OpenAIEmbeddingService(settings)
    vector_store = QdrantKnowledgeStore(settings)
    query_texts = [
        f"Category: {case.category}\nRequirement: {case.query}" for case in cases
    ]
    vectors = await embeddings.embed(query_texts)
    requested_modes: tuple[EvaluationMode, ...] = (
        ("dense", "hybrid") if args.mode == "both" else (args.mode,)
    )
    reports: dict[str, object] = {}
    try:
        for mode in requested_modes:
            result_sets = []
            for query_text, vector in zip(query_texts, vectors, strict=True):
                candidates = await vector_store.search(
                    vector,
                    query_text=query_text,
                    mode=mode,
                    limit=args.top_k,
                )
                async with async_session_factory() as session, session.begin():
                    expanded = await expand_parent_evidence(
                        session,
                        candidates,
                        limit=args.top_k,
                    )
                result_sets.append(expanded)
            reports[mode] = asdict(
                evaluate_retrieval(cases, result_sets, top_k=args.top_k)
            )
    finally:
        await vector_store.close()
        await engine.dispose()
    return {
        "dataset": str(args.dataset),
        "collection": settings.qdrant_collection,
        "embedding_model": settings.embedding_model,
        "reports": reports,
    }


def main() -> None:
    args = _arguments()
    payload = asyncio.run(_evaluate(args))
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
