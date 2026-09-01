import asyncio
from contextlib import suppress
from dataclasses import dataclass

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DeletionConflictError, KnowledgeIndexError, KnowledgeNotFoundError
from app.documents.parser import DocumentParser
from app.documents.pdf import (
    DOCUMENT_IR_CONTENT_TYPE,
    document_ir_object_key,
    serialize_document_ir,
)
from app.infrastructure.storage.minio import ObjectStorageService
from app.models import Document
from app.models.enums import DocumentStatus, DocumentType
from app.models.mixins import generate_uuid, utc_now
from app.rag.chunking import KnowledgeChunker
from app.rag.embedding import EmbeddingService
from app.rag.vector_store import QdrantKnowledgeStore
from app.repositories import DocumentRepository


@dataclass(frozen=True, slots=True)
class KnowledgePage:
    items: list[Document]
    total: int
    offset: int
    limit: int


class KnowledgeService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        storage: ObjectStorageService,
        parser: DocumentParser,
        chunker: KnowledgeChunker,
        embeddings: EmbeddingService,
        vector_store: QdrantKnowledgeStore,
    ) -> None:
        self.session = session
        self.storage = storage
        self.parser = parser
        self.chunker = chunker
        self.embeddings = embeddings
        self.vector_store = vector_store

    async def ingest(
        self,
        upload: UploadFile,
        *,
        title: str,
        category: str,
        version: str | None,
    ) -> Document:
        document_id = generate_uuid()
        stored = await self.storage.upload_knowledge(
            upload,
            document_id=document_id,
            category=category,
        )
        document = Document(
            id=document_id,
            rfp_id=None,
            document_type=DocumentType.KNOWLEDGE.value,
            status=DocumentStatus.INDEXING.value,
            bucket=stored.bucket,
            object_key=stored.object_key,
            original_filename=stored.original_filename,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,
            document_version=version,
            knowledge_category=category.strip().lower(),
            extra_data={"title": title.strip(), "knowledge_status": "ACTIVE"},
        )
        parsed_object_key: str | None = None
        parsed_ir_object_key: str | None = None
        try:
            async with self.session.begin():
                DocumentRepository(self.session).add(document)
                await self.session.flush()
        except Exception:
            await self.storage.remove(stored.bucket, stored.object_key)
            raise

        try:
            content = await self.storage.download(stored.bucket, stored.object_key)
            parsed = await asyncio.to_thread(
                self.parser.parse,
                content,
                stored.original_filename,
                document_id,
            )
            parsed_object_key = f"knowledge/{document_id}/parsed.txt"
            await self.storage.upload_text(parsed_object_key, parsed.text)
            if parsed.document_ir is not None:
                parsed_ir_object_key = document_ir_object_key(document_id)
                await self.storage.upload_text(
                    parsed_ir_object_key,
                    serialize_document_ir(parsed.document_ir),
                    content_type=DOCUMENT_IR_CONTENT_TYPE,
                )
            chunks = self.chunker.split(parsed.text)
            vectors = await self.embeddings.embed([chunk.text for chunk in chunks])
            point_ids = await self.vector_store.index_document(
                document_id=document_id,
                title=title.strip(),
                version=version,
                category=category.strip().lower(),
                chunks=chunks,
                vectors=vectors,
            )
            async with self.session.begin():
                persisted = await DocumentRepository(self.session).get(document_id)
                if persisted is None:
                    raise KnowledgeIndexError("knowledge document disappeared during indexing")
                persisted.status = DocumentStatus.READY.value
                persisted.page_count = parsed.page_count
                persisted.parsed_text_object_key = parsed_object_key
                persisted.parsed_ir_object_key = parsed_ir_object_key
                persisted.extra_data = {
                    **persisted.extra_data,
                    "qdrant_collection": self.vector_store.settings.qdrant_collection,
                    "qdrant_point_count": len(point_ids),
                }
                document = persisted
        except Exception:
            await self._mark_failed(document_id, parsed_object_key, parsed_ir_object_key)
            with suppress(Exception):
                await self.vector_store.delete_document(document_id)
            raise
        return document

    async def list(self, *, offset: int, limit: int) -> KnowledgePage:
        repository = DocumentRepository(self.session)
        async with self.session.begin():
            items = await repository.list_knowledge(offset=offset, limit=limit)
            total = await repository.count_knowledge()
        return KnowledgePage(items=items, total=total, offset=offset, limit=limit)

    async def close(self) -> None:
        await self.vector_store.close()

    async def delete(self, document_id: str) -> None:
        async with self.session.begin():
            document = await DocumentRepository(self.session).get_knowledge_for_update(document_id)
            if document is None:
                raise KnowledgeNotFoundError("知识库文档不存在或已删除")
            if document.status in {DocumentStatus.INDEXING.value, DocumentStatus.PARSING.value}:
                raise DeletionConflictError("文档正在解析或索引，请处理完成后再删除")
            collection = document.extra_data.get("qdrant_collection")
            try:
                await self.vector_store.delete_document(
                    document_id,
                    collection_name=collection if isinstance(collection, str) else None,
                )
            except Exception as exc:
                raise KnowledgeIndexError("知识库索引删除失败，请稍后重试；文档尚未删除") from exc
            document.status = DocumentStatus.ARCHIVED.value
            document.extra_data = {
                **document.extra_data,
                "knowledge_status": "DELETED",
                "deleted_at": utc_now().isoformat(),
                "qdrant_point_count": 0,
            }

    async def _mark_failed(
        self,
        document_id: str,
        parsed_object_key: str | None,
        parsed_ir_object_key: str | None,
    ) -> None:
        try:
            async with self.session.begin():
                document = await DocumentRepository(self.session).get(document_id)
                if document is not None:
                    document.status = DocumentStatus.FAILED.value
                    document.parsed_text_object_key = parsed_object_key
                    document.parsed_ir_object_key = parsed_ir_object_key
        except Exception:
            pass
