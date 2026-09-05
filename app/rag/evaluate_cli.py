from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.rag.embedding import OpenAIEmbeddingService
from app.rag.evaluation import (
    RetrievalEvaluationCase,
    evaluate_retrieval,
    load_evaluation_cases,
)
from app.rag.evaluation_corpus import (
    IndexedEvaluationCorpus,
    expand_evaluation_parent_evidence,
    index_evaluation_corpus,
    load_corpus_manifest,
)
from app.rag.evaluation_report import write_evaluation_report
from app.rag.reranker import CrossEncoderEvidenceReranker
from app.rag.retrieval import expand_parent_evidence
from app.rag.vector_store import QdrantKnowledgeStore, RetrievedEvidence

EvaluationMode = Literal["dense", "hybrid", "hybrid_reranker"]
DEFAULT_DATASET = Path("evals/retrieval/business_queries.jsonl")
DEFAULT_CORPUS_MANIFEST = Path("evals/retrieval/business_corpus.json")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate DealFlow knowledge retrieval")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--mode",
        choices=("dense", "hybrid", "hybrid-reranker", "both", "all"),
        default="all",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--candidate-k",
        type=int,
        help="Hybrid candidates sent to the Cross Encoder; defaults to fusion top K",
    )
    parser.add_argument("--output", type=Path, help="Backward-compatible single JSON output")
    parser.add_argument("--report-dir", type=Path, help="Write JSON, JSONL, and HTML reports")
    parser.add_argument(
        "--isolated",
        action="store_true",
        help="Index a fixed corpus into a temporary Qdrant collection without MySQL or MinIO",
    )
    parser.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS_MANIFEST)
    parser.add_argument("--collection", help="Explicit isolated Qdrant collection name")
    parser.add_argument(
        "--keep-collection",
        action="store_true",
        help="Do not remove the temporary collection after the run",
    )
    parser.add_argument("--reranker-device", choices=("auto", "cuda", "cpu"))
    return parser.parse_args()


def _requested_modes(value: str) -> tuple[EvaluationMode, ...]:
    if value == "both":
        return ("dense", "hybrid")
    if value == "all":
        return ("dense", "hybrid", "hybrid_reranker")
    if value == "hybrid-reranker":
        return ("hybrid_reranker",)
    if value in {"dense", "hybrid"}:
        return (value,)  # type: ignore[return-value]
    raise ValueError(f"unsupported evaluation mode: {value}")


async def _evaluate(args: argparse.Namespace) -> dict[str, object]:
    if args.top_k < 1:
        raise ValueError("top-k must be positive")
    cases = load_evaluation_cases(args.dataset)
    settings = get_settings()
    modes = _requested_modes(args.mode)
    candidate_k = args.candidate_k or settings.qdrant_hybrid_fusion_top_k
    if candidate_k < args.top_k:
        raise ValueError("candidate-k must be at least top-k")

    collection = settings.qdrant_collection
    if args.isolated:
        collection = args.collection or f"dealflow_rag_eval_{uuid4().hex[:12]}"
        settings = settings.model_copy(update={"qdrant_collection": collection})
    reranker_updates: dict[str, object] = {"capability_reranker_enabled": True}
    if args.reranker_device is not None:
        reranker_updates["capability_reranker_device"] = args.reranker_device
    reranker_settings = settings.model_copy(update=reranker_updates)

    embeddings = OpenAIEmbeddingService(settings)
    vector_store = QdrantKnowledgeStore(settings)
    reranker = CrossEncoderEvidenceReranker(reranker_settings)
    indexed_corpus: IndexedEvaluationCorpus | None = None
    index_elapsed_ms: float | None = None

    try:
        if args.isolated:
            if await vector_store.client.collection_exists(collection):
                raise ValueError(
                    f"isolated evaluation collection already exists: {collection}"
                )
            documents = load_corpus_manifest(args.corpus_manifest)
            index_started = perf_counter()
            indexed_corpus = await index_evaluation_corpus(
                documents,
                settings=settings,
                embeddings=embeddings,
                vector_store=vector_store,
            )
            index_elapsed_ms = (perf_counter() - index_started) * 1000

        query_texts = [
            f"Category: {case.category}\nRequirement: {case.query}" for case in cases
        ]
        embedding_started = perf_counter()
        vectors = await embeddings.embed(query_texts)
        query_embedding_elapsed_ms = (perf_counter() - embedding_started) * 1000
        reports: dict[str, object] = {}
        for mode in modes:
            result_sets, latencies_ms = await _evaluate_mode(
                mode,
                cases=cases,
                query_texts=query_texts,
                vectors=vectors,
                top_k=args.top_k,
                candidate_k=candidate_k,
                vector_store=vector_store,
                reranker=reranker,
                indexed_corpus=indexed_corpus,
            )
            reports[mode] = asdict(
                evaluate_retrieval(
                    cases,
                    result_sets,
                    top_k=args.top_k,
                    latencies_ms=latencies_ms,
                )
            )
        return {
            "dataset": str(args.dataset),
            "corpus_manifest": str(args.corpus_manifest) if args.isolated else None,
            "isolated": bool(args.isolated),
            "collection": collection,
            "embedding_model": settings.embedding_model,
            "reranker_model": (
                reranker_settings.capability_reranker_model
                if "hybrid_reranker" in modes
                else None
            ),
            "top_k": args.top_k,
            "candidate_k": candidate_k,
            "indexing": (
                {
                    "document_count": indexed_corpus.document_count,
                    "parent_count": indexed_corpus.parent_count,
                    "child_count": indexed_corpus.child_count,
                    "elapsed_ms": index_elapsed_ms,
                }
                if indexed_corpus is not None
                else None
            ),
            "query_embedding_elapsed_ms": query_embedding_elapsed_ms,
            "reports": reports,
        }
    finally:
        if (
            args.isolated
            and not args.keep_collection
            and await vector_store.client.collection_exists(collection)
        ):
            await vector_store.client.delete_collection(collection)
        await vector_store.close()
        await engine.dispose()


async def _evaluate_mode(
    mode: EvaluationMode,
    *,
    cases: list[RetrievalEvaluationCase],
    query_texts: list[str],
    vectors: list[list[float]],
    top_k: int,
    candidate_k: int,
    vector_store: QdrantKnowledgeStore,
    reranker: CrossEncoderEvidenceReranker,
    indexed_corpus: IndexedEvaluationCorpus | None,
) -> tuple[list[list[RetrievedEvidence]], list[float]]:
    result_sets: list[list[RetrievedEvidence]] = []
    latencies_ms: list[float] = []
    for _case, query_text, vector in zip(cases, query_texts, vectors, strict=True):
        started = perf_counter()
        retrieve_limit = candidate_k if mode == "hybrid_reranker" else top_k
        candidates = await vector_store.search(
            vector,
            query_text=query_text,
            mode="dense" if mode == "dense" else "hybrid",
            limit=retrieve_limit,
        )
        expanded = await _expand(
            candidates,
            limit=retrieve_limit,
            indexed_corpus=indexed_corpus,
        )
        if mode == "hybrid_reranker":
            expanded = await reranker.rerank(query_text, expanded, limit=top_k)
        else:
            expanded = expanded[:top_k]
        latencies_ms.append((perf_counter() - started) * 1000)
        result_sets.append(expanded)
    return result_sets, latencies_ms


async def _expand(
    evidence: list[RetrievedEvidence],
    *,
    limit: int,
    indexed_corpus: IndexedEvaluationCorpus | None,
) -> list[RetrievedEvidence]:
    if indexed_corpus is not None:
        return expand_evaluation_parent_evidence(
            evidence,
            indexed_corpus.parents,
            limit=limit,
        )
    async with async_session_factory() as session, session.begin():
        return await expand_parent_evidence(session, evidence, limit=limit)


def main() -> None:
    args = _arguments()
    payload = asyncio.run(_evaluate(args))
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    if args.report_dir is not None:
        artifacts = write_evaluation_report(payload, args.report_dir)
        print(json.dumps({"artifacts": artifacts}, ensure_ascii=False, indent=2))
    print(serialized)


if __name__ == "__main__":
    main()
