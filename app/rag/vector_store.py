import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Document,
    FieldCondition,
    Filter,
    MatchValue,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    Prefetch,
    Rrf,
    RrfQuery,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.rag.chunking import KnowledgeChunk
from app.rag.hierarchical import ChildChunk, PDFSourceLocation


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    point_id: str
    document_id: str
    title: str
    version: str | None
    category: str
    page_number: int | None
    text: str
    score: float
    page_end: int | None = None
    section_path: tuple[str, ...] = ()
    block_types: tuple[str, ...] = ()
    source_block_ids: tuple[str, ...] = ()
    parent_id: str | None = None
    chunk_id: str | None = None
    matched_child_text: str | None = None
    source_type: str | None = None
    location: dict[str, Any] | None = None
    retrieval_mode: Literal["dense", "hybrid"] = "dense"
    rerank_score: float | None = None


class QdrantKnowledgeStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncQdrantClient(url=settings.qdrant_url)

    async def ensure_collection(self, dimensions: int) -> None:
        if await self.client.collection_exists(self.settings.qdrant_collection):
            return
        try:
            await self.client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config={
                    self.settings.qdrant_dense_vector_name: VectorParams(
                        size=dimensions,
                        distance=Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    self.settings.qdrant_sparse_vector_name: SparseVectorParams(
                        modifier=Modifier.IDF
                    )
                },
            )
        except Exception as exc:
            if not await self.client.collection_exists(self.settings.qdrant_collection):
                raise KnowledgeIndexError("failed to create Qdrant collection") from exc
            return
        try:
            await self._create_payload_indexes()
        except Exception as exc:
            raise KnowledgeIndexError("failed to create Qdrant payload indexes") from exc

    async def _create_payload_indexes(self) -> None:
        for field_name in ("status", "document_id", "parent_id", "category"):
            await self.client.create_payload_index(
                collection_name=self.settings.qdrant_collection,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
                wait=True,
            )

    def _sparse_text(self, text: str) -> Document | SparseVector:
        if self._is_local_client():
            return self._local_sparse_vector(text)
        return Document(
            text=text,
            model=self.settings.qdrant_bm25_model,
            options={
                "tokenizer": "multilingual",
                "stemmer": {"type": "none"},
                "stopwords": {},
            },
        )

    def _is_local_client(self) -> bool:
        return self.client._init_options.get("location") is not None  # noqa: SLF001

    @staticmethod
    def _local_sparse_vector(text: str) -> SparseVector:
        """Provide deterministic lexical vectors for Qdrant's in-memory test backend."""

        normalized = unicodedata.normalize("NFKC", text).lower()
        latin_tokens = re.findall(r"[a-z0-9][a-z0-9._+/#-]*", normalized)
        cjk_runs = re.findall(r"[\u3400-\u9fff]+", normalized)
        tokens = [*latin_tokens]
        for run in cjk_runs:
            tokens.extend(run)
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        counts = Counter(tokens or [normalized])
        weights: dict[int, float] = {}
        for token, frequency in counts.items():
            index = int.from_bytes(
                hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest(),
                "big",
            )
            weights[index] = weights.get(index, 0.0) + 1.0 + math.log(frequency)
        indices = sorted(weights)
        return SparseVector(indices=indices, values=[weights[index] for index in indices])

    async def index_document(
        self,
        *,
        document_id: str,
        title: str,
        version: str | None,
        category: str,
        chunks: Sequence[KnowledgeChunk | ChildChunk],
        vectors: list[list[float]],
    ) -> list[str]:
        if len(chunks) != len(vectors):
            raise KnowledgeIndexError("knowledge chunks and embeddings do not align")
        if not vectors:
            raise KnowledgeIndexError("knowledge document produced no embeddings")
        await self.ensure_collection(len(vectors[0]))
        point_ids: list[str] = []
        points: list[PointStruct] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            parent_id: str | None
            if isinstance(chunk, ChildChunk):
                chunk_index = chunk.order
                point_id = chunk.chunk_id
                location = chunk.location.model_dump(mode="json")
                page = (
                    chunk.location.page_start
                    if isinstance(chunk.location, PDFSourceLocation)
                    else None
                )
                page_end = (
                    chunk.location.page_end
                    if isinstance(chunk.location, PDFSourceLocation)
                    else None
                )
                source_block_ids = chunk.source_node_ids
                source_type = chunk.location.source_type
                chunk_id = chunk.chunk_id
                section_path = chunk.section_path
                block_types = chunk.block_types
                parent_id = chunk.parent_id
                token_count = chunk.token_count
                embedding_token_count = chunk.embedding_token_count
            else:
                chunk_index = chunk.chunk_index
                point_id = str(
                    uuid5(NAMESPACE_URL, f"dealflow:{document_id}:{chunk_index}")
                )
                location = None
                page = chunk.page_number
                page_end = getattr(chunk, "page_end", page)
                source_block_ids = getattr(chunk, "source_block_ids", ())
                source_type = None
                chunk_id = point_id
                section_path = getattr(chunk, "section_path", ())
                block_types = getattr(chunk, "block_types", ())
                parent_id = getattr(chunk, "parent_id", None)
                token_count = None
                embedding_token_count = None
            point_ids.append(point_id)
            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        self.settings.qdrant_dense_vector_name: vector,
                        self.settings.qdrant_sparse_vector_name: self._sparse_text(
                            chunk.embedding_text
                            if isinstance(chunk, ChildChunk)
                            else chunk.text
                        ),
                    },
                    payload={
                        "document_id": document_id,
                        "title": title,
                        "version": version,
                        "page": page,
                        "page_end": page_end,
                        "chunk_index": chunk_index,
                        "chunk_id": chunk_id,
                        "chunk_level": "child",
                        "section_path": list(section_path),
                        "block_types": list(block_types),
                        "source_block_ids": list(source_block_ids),
                        "parent_id": parent_id,
                        "source_type": source_type,
                        "location": location,
                        "token_count": token_count,
                        "embedding_token_count": embedding_token_count,
                        "category": category,
                        "status": "ACTIVE",
                        "text": chunk.text,
                    },
                )
            )
        try:
            await self.client.upsert(
                collection_name=self.settings.qdrant_collection,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise KnowledgeIndexError("failed to index knowledge chunks in Qdrant") from exc
        return point_ids

    async def search(
        self,
        query_vector: list[float],
        *,
        query_text: str | None = None,
        mode: Literal["dense", "hybrid"] = "hybrid",
        limit: int | None = None,
    ) -> list[RetrievedEvidence]:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            return []
        result_limit = limit or self.settings.qdrant_search_top_k
        active_filter = Filter(
            must=[FieldCondition(key="status", match=MatchValue(value="ACTIVE"))]
        )
        if mode == "hybrid" and query_text:
            candidate_limit = max(
                self.settings.qdrant_hybrid_fusion_top_k,
                result_limit * 3,
            )
            response = await self.client.query_points(
                collection_name=self.settings.qdrant_collection,
                prefetch=[
                    Prefetch(
                        query=query_vector,
                        using=self.settings.qdrant_dense_vector_name,
                        filter=active_filter,
                        limit=self.settings.qdrant_dense_prefetch_top_k,
                        score_threshold=self.settings.qdrant_score_threshold,
                    ),
                    Prefetch(
                        query=self._sparse_text(query_text),
                        using=self.settings.qdrant_sparse_vector_name,
                        filter=active_filter,
                        limit=self.settings.qdrant_sparse_prefetch_top_k,
                    ),
                ],
                query=RrfQuery(rrf=Rrf()),
                query_filter=active_filter,
                limit=candidate_limit,
                with_payload=True,
            )
            retrieval_mode: Literal["dense", "hybrid"] = "hybrid"
        else:
            response = await self.client.query_points(
                collection_name=self.settings.qdrant_collection,
                query=query_vector,
                using=self.settings.qdrant_dense_vector_name,
                query_filter=active_filter,
                limit=result_limit * 3,
                with_payload=True,
                score_threshold=self.settings.qdrant_score_threshold,
            )
            retrieval_mode = "dense"
        evidence: list[RetrievedEvidence] = []
        for point in response.points:
            payload: dict[str, Any] = dict(point.payload or {})
            document_id = payload.get("document_id")
            text = payload.get("text")
            if not isinstance(document_id, str) or not isinstance(text, str):
                continue
            page = payload.get("page")
            page_end = payload.get("page_end")
            section_path = payload.get("section_path")
            block_types = payload.get("block_types")
            source_block_ids = payload.get("source_block_ids")
            parent_id = payload.get("parent_id")
            chunk_id = payload.get("chunk_id")
            source_type = payload.get("source_type")
            location = payload.get("location")
            evidence.append(
                RetrievedEvidence(
                    point_id=str(point.id),
                    document_id=document_id,
                    title=str(payload.get("title") or "Untitled knowledge document"),
                    version=str(payload["version"]) if payload.get("version") else None,
                    category=str(payload.get("category") or "general"),
                    page_number=page if isinstance(page, int) else None,
                    text=text,
                    score=float(point.score),
                    page_end=page_end if isinstance(page_end, int) else None,
                    section_path=(
                        tuple(item for item in section_path if isinstance(item, str))
                        if isinstance(section_path, list)
                        else ()
                    ),
                    block_types=(
                        tuple(item for item in block_types if isinstance(item, str))
                        if isinstance(block_types, list)
                        else ()
                    ),
                    source_block_ids=(
                        tuple(item for item in source_block_ids if isinstance(item, str))
                        if isinstance(source_block_ids, list)
                        else ()
                    ),
                    parent_id=parent_id if isinstance(parent_id, str) else None,
                    chunk_id=chunk_id if isinstance(chunk_id, str) else None,
                    source_type=source_type if isinstance(source_type, str) else None,
                    location=location if isinstance(location, dict) else None,
                    retrieval_mode=retrieval_mode,
                )
            )
        return evidence

    async def delete_document(
        self, document_id: str, *, collection_name: str | None = None
    ) -> None:
        collection = collection_name or self.settings.qdrant_collection
        if not await self.client.collection_exists(collection):
            return
        await self.client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            wait=True,
        )

    async def close(self) -> None:
        await self.client.close()
