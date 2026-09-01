from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.rag.chunking import KnowledgeChunk


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
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
            )
        except Exception as exc:
            if not await self.client.collection_exists(self.settings.qdrant_collection):
                raise KnowledgeIndexError("failed to create Qdrant collection") from exc

    async def index_document(
        self,
        *,
        document_id: str,
        title: str,
        version: str | None,
        category: str,
        chunks: list[KnowledgeChunk],
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
            point_id = str(uuid5(NAMESPACE_URL, f"dealflow:{document_id}:{chunk.chunk_index}"))
            point_ids.append(point_id)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "title": title,
                        "version": version,
                        "page": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
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
        limit: int | None = None,
    ) -> list[RetrievedEvidence]:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            return []
        response = await self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=query_vector,
            query_filter=Filter(
                must=[FieldCondition(key="status", match=MatchValue(value="ACTIVE"))]
            ),
            limit=limit or self.settings.qdrant_search_top_k,
            with_payload=True,
            score_threshold=self.settings.qdrant_score_threshold,
        )
        evidence: list[RetrievedEvidence] = []
        for point in response.points:
            payload: dict[str, Any] = dict(point.payload or {})
            document_id = payload.get("document_id")
            text = payload.get("text")
            if not isinstance(document_id, str) or not isinstance(text, str):
                continue
            page = payload.get("page")
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
