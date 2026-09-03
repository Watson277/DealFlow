"""Backfill document and Child hashes for knowledge indexed before incremental updates."""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import async_session_factory, close_database
from app.infrastructure.storage.minio import ObjectStorageService
from app.models import Document
from app.models.enums import DocumentStatus, DocumentType
from app.rag.hierarchical import KnowledgeChunkBundle
from app.rag.incremental import ChildDecision, candidates_for, document_content_hash
from app.rag.vector_store import QdrantKnowledgeStore
from app.repositories import DocumentRepository, KnowledgeChunkRepository

logger = structlog.get_logger(__name__)


async def backfill() -> None:
    settings = get_settings()
    storage = ObjectStorageService(settings)
    vector_store = QdrantKnowledgeStore(settings)
    try:
        async with async_session_factory() as session:
            async with session.begin():
                documents = list(
                    (
                        await session.scalars(
                            select(Document).where(
                                Document.document_type == DocumentType.KNOWLEDGE.value,
                                Document.status != DocumentStatus.ARCHIVED.value,
                                Document.content_hash.is_(None),
                            )
                        )
                    ).all()
                )

            for document in documents:
                if not document.parsed_text_object_key:
                    logger.warning(
                        "incremental_backfill_skipped_missing_text",
                        document_id=document.id,
                    )
                    continue
                parsed_text = (
                    await storage.download(document.bucket, document.parsed_text_object_key)
                ).decode("utf-8")
                content_hash = document_content_hash(parsed_text)
                decisions: tuple[ChildDecision, ...] = ()
                point_ids: dict[str, str] = {}
                chunks_key = document.extra_data.get("chunks_object_key")
                if isinstance(chunks_key, str):
                    serialized = (await storage.download(document.bucket, chunks_key)).decode(
                        "utf-8"
                    )
                    bundle = KnowledgeChunkBundle.model_validate_json(serialized)
                    candidates = candidates_for(
                        bundle.children,
                        model=settings.embedding_model,
                        dimensions=settings.embedding_dimensions,
                    )
                    collection = document.extra_data.get("qdrant_collection")
                    point_ids = await vector_store.document_point_ids(
                        document.id,
                        collection_name=collection if isinstance(collection, str) else None,
                    )
                    if all(candidate.chunk.chunk_id in point_ids for candidate in candidates):
                        decisions = tuple(
                            ChildDecision(candidate=candidate, kind="ADDED")
                            for candidate in candidates
                        )
                    else:
                        logger.warning(
                            "incremental_backfill_skipped_child_indexes",
                            document_id=document.id,
                            expected=len(candidates),
                            found=len(point_ids),
                        )

                async with session.begin():
                    current = await DocumentRepository(session).get_knowledge_for_update(
                        document.id
                    )
                    if current is None or current.content_hash is not None:
                        continue
                    current.content_hash = content_hash
                    if decisions:
                        await KnowledgeChunkRepository(session).replace_child_indexes(
                            document.id,
                            decisions,
                            point_ids,
                        )
                logger.info(
                    "incremental_backfill_completed",
                    document_id=document.id,
                    child_indexes=len(decisions),
                )
    finally:
        await vector_store.close()
        await close_database()


if __name__ == "__main__":
    asyncio.run(backfill())
