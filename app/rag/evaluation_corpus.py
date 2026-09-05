from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.core.config import Settings
from app.documents.parser import DocumentParser
from app.rag.embedding import EmbeddingService
from app.rag.hierarchical import (
    DocxStructureAdapter,
    HierarchicalKnowledgeChunker,
    MarkdownStructureAdapter,
    ParentChunk,
    PDFStructureAdapter,
)
from app.rag.retrieval import group_child_evidence
from app.rag.vector_store import QdrantKnowledgeStore, RetrievedEvidence


@dataclass(frozen=True, slots=True)
class EvaluationCorpusDocument:
    document_key: str
    path: Path
    title: str
    category: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class IndexedEvaluationCorpus:
    document_count: int
    parent_count: int
    child_count: int
    parents: dict[str, ParentChunk]


def load_corpus_manifest(path: Path) -> list[EvaluationCorpusDocument]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_documents = payload["documents"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid evaluation corpus manifest: {path}") from exc
    if not isinstance(raw_documents, list) or not raw_documents:
        raise ValueError("evaluation corpus manifest contains no documents")

    documents: list[EvaluationCorpusDocument] = []
    for index, item in enumerate(raw_documents, start=1):
        try:
            document_path = (path.parent / str(item["path"])).resolve()
            document = EvaluationCorpusDocument(
                document_key=str(item["document_key"]).strip(),
                path=document_path,
                title=str(item["title"]).strip(),
                category=str(item["category"]).strip().lower(),
                version=(str(item["version"]).strip() if item.get("version") else None),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"invalid corpus document at position {index}") from exc
        if not document.document_key or not document.title or not document.category:
            raise ValueError(f"empty corpus document field at position {index}")
        if not document.path.is_file():
            raise ValueError(f"evaluation corpus file does not exist: {document.path}")
        documents.append(document)

    keys = [document.document_key for document in documents]
    if len(keys) != len(set(keys)):
        raise ValueError("evaluation corpus document_key values must be unique")
    return documents


async def index_evaluation_corpus(
    documents: list[EvaluationCorpusDocument],
    *,
    settings: Settings,
    embeddings: EmbeddingService,
    vector_store: QdrantKnowledgeStore,
) -> IndexedEvaluationCorpus:
    parser = DocumentParser.from_settings(settings)
    chunker = HierarchicalKnowledgeChunker(settings)
    parents: dict[str, ParentChunk] = {}
    child_count = 0

    for document in documents:
        document_id = str(
            uuid5(NAMESPACE_URL, f"dealflow:rag-evaluation:{document.document_key}")
        )
        parsed = parser.parse(
            document.path.read_bytes(),
            document.path.name,
            document_id,
        )
        if parsed.document_ir is not None:
            structural = PDFStructureAdapter.convert(
                parsed.document_ir,
                document_id=document_id,
                title=document.title,
                version=document.version,
            )
        elif document.path.suffix.lower() in {".md", ".markdown"}:
            structural = MarkdownStructureAdapter.convert(
                parsed.text,
                document_id=document_id,
                title=document.title,
                version=document.version,
            )
        else:
            structural = DocxStructureAdapter.convert(
                parsed.text,
                document_id=document_id,
                title=document.title,
                version=document.version,
            )
        bundle = chunker.split(structural)
        vectors = await embeddings.embed([child.embedding_text for child in bundle.children])
        await vector_store.index_document(
            document_id=document_id,
            title=document.title,
            version=document.version,
            category=document.category,
            chunks=bundle.children,
            vectors=vectors,
        )
        parents.update((parent.chunk_id, parent) for parent in bundle.parents)
        child_count += len(bundle.children)

    return IndexedEvaluationCorpus(
        document_count=len(documents),
        parent_count=len(parents),
        child_count=child_count,
        parents=parents,
    )


def expand_evaluation_parent_evidence(
    evidence: list[RetrievedEvidence],
    parents: dict[str, ParentChunk],
    *,
    limit: int,
) -> list[RetrievedEvidence]:
    expanded: list[RetrievedEvidence] = []
    for item in group_child_evidence(evidence):
        parent = parents.get(item.parent_id) if item.parent_id is not None else None
        expanded.append(
            replace(
                item,
                text=parent.text if parent is not None else item.text,
                matched_child_text=item.text if parent is not None else None,
            )
        )
        if len(expanded) >= limit:
            break
    return expanded
