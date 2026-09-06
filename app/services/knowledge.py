import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import structlog
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DeletionConflictError,
    DuplicateKnowledgeError,
    KnowledgeIndexError,
    KnowledgeNotFoundError,
)
from app.documents.parser import DocumentParser, ParsedDocument
from app.documents.pdf import (
    DOCUMENT_IR_CONTENT_TYPE,
    DOCUMENT_IR_FILENAME,
    document_ir_object_key,
    serialize_document_ir,
)
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.infrastructure.storage.local_artifacts import LocalArtifactExporter
from app.infrastructure.storage.minio import ObjectStorageService
from app.models import Document, OutboxEvent
from app.models.enums import DocumentStatus, DocumentType, OutboxStatus
from app.models.mixins import generate_uuid, utc_now
from app.rag.chunking import KnowledgeChunker
from app.rag.embedding import EmbeddingService
from app.rag.hierarchical import (
    KNOWLEDGE_CHUNK_CONTENT_TYPE,
    KNOWLEDGE_CHUNK_FILENAME,
    DocxStructureAdapter,
    HierarchicalKnowledgeChunker,
    KnowledgeChunkBundle,
    MarkdownStructureAdapter,
    PDFStructureAdapter,
    knowledge_chunk_object_key,
    serialize_knowledge_chunks,
)
from app.rag.incremental import (
    ChildDecision,
    candidates_for,
    classify_children,
    document_content_hash,
)
from app.rag.vector_store import QdrantKnowledgeStore
from app.repositories import (
    DocumentRepository,
    KnowledgeChunkRepository,
    OutboxEventRepository,
)

logger = structlog.get_logger(__name__)


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
        local_exporter: LocalArtifactExporter | None = None,
        outbox_publisher: OutboxPublisher | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.parser = parser
        self.chunker = chunker
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.local_exporter = local_exporter
        self.outbox_publisher = outbox_publisher

    async def enqueue_ingestion(
        self,
        upload: UploadFile,
        *,
        title: str,
        category: str,
        version: str | None,
    ) -> Document:
        if self.outbox_publisher is None:
            raise RuntimeError("knowledge ingestion requires an Outbox publisher")

        document_id = generate_uuid()
        event_id = generate_uuid()
        normalized_title = title.strip()
        normalized_category = category.strip().lower()
        stored = await self.storage.upload_knowledge(
            upload,
            document_id=document_id,
            category=normalized_category,
        )
        document = Document(
            id=document_id,
            rfp_id=None,
            document_type=DocumentType.KNOWLEDGE.value,
            status=DocumentStatus.UPLOADED.value,
            bucket=stored.bucket,
            object_key=stored.object_key,
            original_filename=stored.original_filename,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,
            document_version=version,
            knowledge_category=normalized_category,
            extra_data={
                "title": normalized_title,
                "knowledge_status": "ACTIVE",
                "ingestion_stage": "QUEUED",
                "ingestion_error": None,
            },
        )
        event = OutboxEvent(
            id=event_id,
            aggregate_type="KnowledgeDocument",
            aggregate_id=document_id,
            topic=self.vector_store.settings.kafka_knowledge_ingestion_topic,
            event_key=document_id,
            payload={
                "event_id": event_id,
                "event_type": "knowledge.ingestion.requested",
                "occurred_at": datetime.now(UTC).isoformat(),
                "document_id": document_id,
            },
            status=OutboxStatus.PENDING.value,
        )

        try:
            async with self.session.begin():
                repository = DocumentRepository(self.session)
                duplicate = await repository.find_active_knowledge_by_checksum(
                    stored.checksum_sha256
                )
                if duplicate is not None:
                    raise DuplicateKnowledgeError(
                        duplicate.id,
                        str(duplicate.extra_data.get("title") or duplicate.original_filename),
                    )
                repository.add(document)
                OutboxEventRepository(self.session).add(event)
                await self.session.flush()
        except Exception:
            await self.storage.remove(stored.bucket, stored.object_key)
            raise

        event_status = await self.outbox_publisher.publish_event(self.session, event)
        logger.info(
            "knowledge_ingestion_queued",
            document_id=document_id,
            event_id=event_id,
            event_status=event_status,
        )
        return document

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
        try:
            async with self.session.begin():
                DocumentRepository(self.session).add(document)
                await self.session.flush()
        except Exception:
            await self.storage.remove(stored.bucket, stored.object_key)
            raise

        try:
            document = await self._process_existing_document(document_id)
        except DuplicateKnowledgeError:
            await self._discard_new_document(document_id, stored.bucket, stored.object_key)
            raise
        except Exception as exc:
            failure_recorded = await self._mark_failed(
                document_id,
                None,
                None,
                None,
                error=exc,
            )
            if not failure_recorded:
                raise
            with suppress(Exception):
                await self.vector_store.delete_document(document_id)
            raise
        return document

    async def process_queued_ingestion(self, document_id: str) -> None:
        try:
            document = await self._process_existing_document(document_id)
            if document is None:
                return
        except Exception as exc:
            failure_recorded = await self._mark_failed(
                document_id,
                None,
                None,
                None,
                error=exc,
            )
            if not failure_recorded:
                raise
            with suppress(Exception):
                await self.vector_store.delete_document(document_id)
            logger.warning(
                "knowledge_ingestion_failed",
                document_id=document_id,
                error_type=type(exc).__name__,
            )
            return
        logger.info("knowledge_ingestion_completed", document_id=document_id)

    async def _process_existing_document(self, document_id: str) -> Document | None:
        async with self.session.begin():
            document = await DocumentRepository(self.session).get_knowledge_for_update(document_id)
            if document is None:
                logger.info("knowledge_ingestion_ignored_missing_document", document_id=document_id)
                return None
            if document.status == DocumentStatus.READY.value:
                logger.info("knowledge_ingestion_already_completed", document_id=document_id)
                return document
            document.status = DocumentStatus.PARSING.value
            document.extra_data = {
                **document.extra_data,
                "ingestion_stage": "PARSING",
                "ingestion_error": None,
            }

        title = str(document.extra_data.get("title") or document.original_filename)
        category = document.knowledge_category or "general"
        version = document.document_version
        content = await self.storage.download(document.bucket, document.object_key)
        parsed = await asyncio.to_thread(
            self.parser.parse,
            content,
            document.original_filename,
            document_id,
        )
        normalized_content_hash = document_content_hash(parsed.text)
        async with self.session.begin():
            repository = DocumentRepository(self.session)
            persisted = await repository.get_knowledge_for_update(document_id)
            if persisted is None:
                logger.info("knowledge_ingestion_cancelled", document_id=document_id)
                return None
            duplicate = await repository.find_active_knowledge_by_content_hash(
                normalized_content_hash,
                exclude_document_id=document_id,
            )
            if duplicate is not None:
                raise DuplicateKnowledgeError(
                    duplicate.id,
                    str(duplicate.extra_data.get("title") or duplicate.original_filename),
                )
            persisted.status = DocumentStatus.INDEXING.value
            persisted.extra_data = {
                **persisted.extra_data,
                "ingestion_stage": "INDEXING",
            }

        parsed_object_key = f"knowledge/{document_id}/parsed.txt"
        await self.storage.upload_text(parsed_object_key, parsed.text)
        parsed_ir_object_key: str | None = None
        if parsed.document_ir is not None:
            parsed_ir_object_key = document_ir_object_key(document_id)
            await self.storage.upload_text(
                parsed_ir_object_key,
                serialize_document_ir(parsed.document_ir),
                content_type=DOCUMENT_IR_CONTENT_TYPE,
            )
        bundle = self._build_bundle(
            parsed,
            filename=document.original_filename,
            document_id=document_id,
            title=title,
            version=version,
        )
        child_candidates = candidates_for(
            bundle.children,
            model=self.vector_store.settings.embedding_model,
            dimensions=self.vector_store.settings.embedding_dimensions,
        )
        decisions = tuple(
            ChildDecision(candidate=candidate, kind="ADDED")
            for candidate in child_candidates
        )
        chunks_object_key = knowledge_chunk_object_key(document_id)
        serialized_chunks = serialize_knowledge_chunks(bundle)
        await self.storage.upload_text(
            chunks_object_key,
            serialized_chunks,
            content_type=KNOWLEDGE_CHUNK_CONTENT_TYPE,
        )
        vectors = await self.embeddings.embed(
            [chunk.embedding_text for chunk in bundle.children]
        )
        point_ids = await self.vector_store.index_document(
            document_id=document_id,
            title=title,
            version=version,
            category=category,
            chunks=bundle.children,
            vectors=vectors,
        )
        async with self.session.begin():
            persisted = await DocumentRepository(self.session).get_knowledge_for_update(document_id)
            if persisted is None:
                await self.vector_store.delete_document(document_id)
                logger.info("knowledge_ingestion_cancelled", document_id=document_id)
                return None
            await KnowledgeChunkRepository(self.session).replace_parents(
                document_id,
                bundle.parents,
            )
            await KnowledgeChunkRepository(self.session).replace_child_indexes(
                document_id,
                decisions,
                dict(zip((item.chunk_id for item in bundle.children), point_ids, strict=True)),
            )
            persisted.status = DocumentStatus.READY.value
            persisted.content_hash = normalized_content_hash
            persisted.page_count = parsed.page_count
            persisted.parsed_text_object_key = parsed_object_key
            persisted.parsed_ir_object_key = parsed_ir_object_key
            persisted.extra_data = {
                **persisted.extra_data,
                "ingestion_stage": "READY",
                "ingestion_error": None,
                "qdrant_collection": self.vector_store.settings.qdrant_collection,
                "qdrant_point_count": len(point_ids),
                "chunks_object_key": chunks_object_key,
                "parent_chunk_count": len(bundle.parents),
                "child_chunk_count": len(bundle.children),
                "chunk_schema_version": bundle.schema_version,
                "incremental_stats": {
                    "unchanged": 0,
                    "moved": 0,
                    "modified": 0,
                    "added": len(bundle.children),
                    "deleted": 0,
                    "embedded": len(bundle.children),
                },
            }
            document = persisted
        await self._export_locally(
            document_id=document_id,
            original_filename=document.original_filename,
            parsed_text=parsed.text,
            document_ir=(
                serialize_document_ir(parsed.document_ir)
                if parsed.document_ir is not None
                else None
            ),
            serialized_chunks=serialized_chunks,
            parsed_object_key=parsed_object_key,
            parsed_ir_object_key=parsed_ir_object_key,
            chunks_object_key=chunks_object_key,
        )
        return document

    async def update(
        self,
        document_id: str,
        upload: UploadFile,
        *,
        title: str,
        category: str,
        version: str | None,
    ) -> Document:
        revision_id = generate_uuid()
        normalized_title = title.strip()
        normalized_category = category.strip().lower()
        previous_content_hash: str | None = None
        old_collection: str | None = None
        async with self.session.begin():
            document = await DocumentRepository(self.session).get_knowledge_for_update(document_id)
            if document is None:
                raise KnowledgeNotFoundError("知识库文档不存在或已删除")
            if document.status in {DocumentStatus.INDEXING.value, DocumentStatus.PARSING.value}:
                raise DeletionConflictError("文档正在解析或索引，请稍后重试")
            previous_content_hash = document.content_hash
            configured_collection = document.extra_data.get("qdrant_collection")
            old_collection = (
                configured_collection if isinstance(configured_collection, str) else None
            )
            document.status = DocumentStatus.INDEXING.value

        stored = None
        parsed_object_key: str | None = None
        parsed_ir_object_key: str | None = None
        chunks_object_key: str | None = None
        indexed_point_ids: list[str] = []
        qdrant_mutated = False
        try:
            stored = await self.storage.upload_knowledge(
                upload,
                document_id=document_id,
                category=normalized_category,
                revision_id=revision_id,
            )
            content = await self.storage.download(stored.bucket, stored.object_key)
            parsed = await asyncio.to_thread(
                self.parser.parse,
                content,
                stored.original_filename,
                document_id,
            )
            normalized_content_hash = document_content_hash(parsed.text)
            if normalized_content_hash == previous_content_hash:
                raise DuplicateKnowledgeError(document_id, normalized_title)
            async with self.session.begin():
                repository = DocumentRepository(self.session)
                duplicate = await repository.find_active_knowledge_by_content_hash(
                    normalized_content_hash,
                    exclude_document_id=document_id,
                )
                old_children = await KnowledgeChunkRepository(
                    self.session
                ).list_child_indexes(document_id)
            if duplicate is not None:
                raise DuplicateKnowledgeError(
                    duplicate.id,
                    str(duplicate.extra_data.get("title") or duplicate.original_filename),
                )
            bundle = self._build_bundle(
                parsed,
                filename=stored.original_filename,
                document_id=document_id,
                title=normalized_title,
                version=version,
            )
            candidates = candidates_for(
                bundle.children,
                model=self.vector_store.settings.embedding_model,
                dimensions=self.vector_store.settings.embedding_dimensions,
            )
            legacy_rebuild = not old_children
            changes = classify_children(old_children, candidates)
            if legacy_rebuild:
                await self.vector_store.delete_document(
                    document_id,
                    collection_name=old_collection,
                )
                qdrant_mutated = True
            point_ids_by_chunk: dict[str, str] = {}
            for decision in changes.of_kind("UNCHANGED", "MOVED"):
                if decision.previous is None:
                    raise KnowledgeIndexError("incremental retained Chunk lost its old Point")
                point_ids_by_chunk[decision.candidate.chunk.chunk_id] = (
                    decision.previous.qdrant_point_id
                )

            changed = changes.of_kind("MODIFIED", "ADDED")
            if changed:
                vectors = await self.embeddings.embed(
                    [item.candidate.chunk.embedding_text for item in changed]
                )
                requested_point_ids = [
                    str(
                        uuid5(
                            NAMESPACE_URL,
                            (
                                f"dealflow:{document_id}:revision:{revision_id}:"
                                f"{item.candidate.chunk.chunk_id}"
                            ),
                        )
                    )
                    for item in changed
                ]
                indexed_point_ids = await self.vector_store.index_document(
                    document_id=document_id,
                    title=normalized_title,
                    version=version,
                    category=normalized_category,
                    chunks=[item.candidate.chunk for item in changed],
                    vectors=vectors,
                    point_ids=requested_point_ids,
                )
                point_ids_by_chunk.update(
                    zip(
                        (item.candidate.chunk.chunk_id for item in changed),
                        indexed_point_ids,
                        strict=True,
                    )
                )
                qdrant_mutated = True

            for decision in changes.of_kind("UNCHANGED", "MOVED"):
                point_id = point_ids_by_chunk[decision.candidate.chunk.chunk_id]
                await self.vector_store.update_child_payload(
                    point_id=point_id,
                    document_id=document_id,
                    title=normalized_title,
                    version=version,
                    category=normalized_category,
                    chunk=decision.candidate.chunk,
                )
                qdrant_mutated = True

            retained_old_point_ids = {
                item.previous.qdrant_point_id
                for item in changes.of_kind("UNCHANGED", "MOVED")
                if item.previous is not None
            }
            obsolete_point_ids = [
                item.qdrant_point_id
                for item in old_children
                if item.qdrant_point_id not in retained_old_point_ids
            ]
            await self.vector_store.delete_points(
                obsolete_point_ids,
                collection_name=old_collection,
            )
            if obsolete_point_ids:
                qdrant_mutated = True

            parsed_object_key = (
                f"knowledge/{document_id}/versions/{revision_id}/parsed.txt"
            )
            await self.storage.upload_text(parsed_object_key, parsed.text)
            if parsed.document_ir is not None:
                parsed_ir_object_key = (
                    f"documents/{document_id}/versions/{revision_id}/{DOCUMENT_IR_FILENAME}"
                )
                await self.storage.upload_text(
                    parsed_ir_object_key,
                    serialize_document_ir(parsed.document_ir),
                    content_type=DOCUMENT_IR_CONTENT_TYPE,
                )
            chunks_object_key = (
                f"documents/{document_id}/versions/{revision_id}/{KNOWLEDGE_CHUNK_FILENAME}"
            )
            serialized_chunks = serialize_knowledge_chunks(bundle)
            await self.storage.upload_text(
                chunks_object_key,
                serialized_chunks,
                content_type=KNOWLEDGE_CHUNK_CONTENT_TYPE,
            )

            stats = {
                "unchanged": len(changes.of_kind("UNCHANGED")),
                "moved": len(changes.of_kind("MOVED")),
                "modified": len(changes.of_kind("MODIFIED")),
                "added": len(changes.of_kind("ADDED")),
                "deleted": len(changes.deleted),
                "embedded": len(changed),
                "legacy_full_rebuild": legacy_rebuild,
            }
            async with self.session.begin():
                persisted = await DocumentRepository(self.session).get_knowledge_for_update(
                    document_id
                )
                if persisted is None:
                    raise KnowledgeIndexError("knowledge document disappeared during update")
                chunk_repository = KnowledgeChunkRepository(self.session)
                await chunk_repository.replace_parents(document_id, bundle.parents)
                await chunk_repository.replace_child_indexes(
                    document_id,
                    changes.decisions,
                    point_ids_by_chunk,
                )
                persisted.status = DocumentStatus.READY.value
                persisted.bucket = stored.bucket
                persisted.object_key = stored.object_key
                persisted.original_filename = stored.original_filename
                persisted.content_type = stored.content_type
                persisted.size_bytes = stored.size_bytes
                persisted.checksum_sha256 = stored.checksum_sha256
                persisted.content_hash = normalized_content_hash
                persisted.page_count = parsed.page_count
                persisted.document_version = version
                persisted.knowledge_category = normalized_category
                persisted.parsed_text_object_key = parsed_object_key
                persisted.parsed_ir_object_key = parsed_ir_object_key
                persisted.extra_data = {
                    **persisted.extra_data,
                    "title": normalized_title,
                    "knowledge_status": "ACTIVE",
                    "qdrant_collection": self.vector_store.settings.qdrant_collection,
                    "qdrant_point_count": len(bundle.children),
                    "chunks_object_key": chunks_object_key,
                    "parent_chunk_count": len(bundle.parents),
                    "child_chunk_count": len(bundle.children),
                    "chunk_schema_version": bundle.schema_version,
                    "last_revision_id": revision_id,
                    "incremental_stats": stats,
                    "last_update_error": None,
                }
                document = persisted
            await self._export_locally(
                document_id=document_id,
                original_filename=stored.original_filename,
                parsed_text=parsed.text,
                document_ir=(
                    serialize_document_ir(parsed.document_ir)
                    if parsed.document_ir is not None
                    else None
                ),
                serialized_chunks=serialized_chunks,
                parsed_object_key=parsed_object_key,
                parsed_ir_object_key=parsed_ir_object_key,
                chunks_object_key=chunks_object_key,
            )
            return document
        except DuplicateKnowledgeError:
            await self._restore_after_update_failure(
                document_id,
                error=None,
                failed=qdrant_mutated,
            )
            if stored is not None:
                with suppress(Exception):
                    await self.storage.remove(stored.bucket, stored.object_key)
            raise
        except Exception as exc:
            if indexed_point_ids and not qdrant_mutated:
                with suppress(Exception):
                    await self.vector_store.delete_points(indexed_point_ids)
            await self._restore_after_update_failure(
                document_id,
                error=exc,
                failed=qdrant_mutated,
            )
            raise

    async def _restore_after_update_failure(
        self,
        document_id: str,
        *,
        error: Exception | None,
        failed: bool,
    ) -> None:
        with suppress(Exception):
            async with self.session.begin():
                document = await DocumentRepository(self.session).get(document_id)
                if document is not None and document.status == DocumentStatus.INDEXING.value:
                    document.status = (
                        DocumentStatus.FAILED.value if failed else DocumentStatus.READY.value
                    )
                    document.extra_data = {
                        **document.extra_data,
                        "last_update_error": (
                            f"{type(error).__name__}: {str(error)[:1000]}"
                            if error is not None
                            else None
                        ),
                    }

    async def _discard_new_document(self, document_id: str, bucket: str, object_key: str) -> None:
        with suppress(Exception):
            async with self.session.begin():
                document = await DocumentRepository(self.session).get(document_id)
                if document is not None:
                    await self.session.delete(document)
        with suppress(Exception):
            await self.storage.remove(bucket, object_key)

    def _build_bundle(
        self,
        parsed: ParsedDocument,
        *,
        filename: str,
        document_id: str,
        title: str,
        version: str | None,
    ) -> KnowledgeChunkBundle:
        source_extension = Path(filename).suffix.lower()
        if parsed.document_ir is not None:
            structural_document = PDFStructureAdapter.convert(
                parsed.document_ir,
                document_id=document_id,
                title=title,
                version=version,
            )
        elif source_extension in {".md", ".markdown"}:
            structural_document = MarkdownStructureAdapter.convert(
                parsed.text,
                document_id=document_id,
                title=title,
                version=version,
            )
        else:
            structural_document = DocxStructureAdapter.convert(
                parsed.text,
                document_id=document_id,
                title=title,
                version=version,
            )
        return HierarchicalKnowledgeChunker(self.vector_store.settings).split(
            structural_document
        )

    async def _export_locally(
        self,
        *,
        document_id: str,
        original_filename: str,
        parsed_text: str,
        document_ir: str | None,
        serialized_chunks: str,
        parsed_object_key: str,
        parsed_ir_object_key: str | None,
        chunks_object_key: str,
    ) -> None:
        if self.local_exporter is None:
            return
        artifacts = {
            "parsed.md": parsed_text,
            KNOWLEDGE_CHUNK_FILENAME: serialized_chunks,
        }
        if document_ir is not None:
            artifacts[DOCUMENT_IR_FILENAME] = document_ir
        try:
            directory = await asyncio.to_thread(
                self.local_exporter.export,
                kind="knowledge",
                document_id=document_id,
                original_filename=original_filename,
                artifacts=artifacts,
                metadata={
                    "parsed_text_object_key": parsed_object_key,
                    "parsed_ir_object_key": parsed_ir_object_key,
                    "chunks_object_key": chunks_object_key,
                },
            )
        except Exception as exc:
            logger.warning(
                "knowledge_local_artifact_export_failed",
                document_id=document_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return
        if directory is not None:
            logger.info(
                "knowledge_local_artifacts_exported",
                document_id=document_id,
                directory=str(directory),
            )

    async def list(self, *, offset: int, limit: int) -> KnowledgePage:
        repository = DocumentRepository(self.session)
        async with self.session.begin():
            items = await repository.list_knowledge(offset=offset, limit=limit)
            total = await repository.count_knowledge()
        return KnowledgePage(items=items, total=total, offset=offset, limit=limit)

    async def get(self, document_id: str) -> Document:
        async with self.session.begin():
            document = await DocumentRepository(self.session).get_knowledge(document_id)
        if document is None:
            raise KnowledgeNotFoundError("知识库文档不存在或已删除")
        return document

    async def close(self) -> None:
        await self.vector_store.close()

    async def delete(self, document_id: str) -> None:
        async with self.session.begin():
            document = await DocumentRepository(self.session).get_knowledge_for_update(document_id)
            if document is None:
                raise KnowledgeNotFoundError("知识库文档不存在或已删除")
            if document.status in {DocumentStatus.INDEXING.value, DocumentStatus.PARSING.value}:
                raise DeletionConflictError("文档正在解析或索引，请处理完成后再删除")
            stored_collection = document.extra_data.get("qdrant_collection")
            current_collection = self.vector_store.settings.qdrant_collection
            collections = tuple(
                dict.fromkeys(
                    collection
                    for collection in (
                        stored_collection if isinstance(stored_collection, str) else None,
                        current_collection,
                    )
                    if collection
                )
            )
            try:
                for collection in collections:
                    await self.vector_store.delete_document(
                        document_id,
                        collection_name=collection,
                    )
            except Exception as exc:
                raise KnowledgeIndexError("知识库索引删除失败，请稍后重试；文档尚未删除") from exc
            document.status = DocumentStatus.ARCHIVED.value
            document.extra_data = {
                **document.extra_data,
                "knowledge_status": "DELETED",
                "deleted_at": utc_now().isoformat(),
                "qdrant_point_count": 0,
                "qdrant_deleted_collections": list(collections),
            }

    async def _mark_failed(
        self,
        document_id: str,
        parsed_object_key: str | None,
        parsed_ir_object_key: str | None,
        chunks_object_key: str | None,
        *,
        error: Exception | None = None,
    ) -> bool:
        try:
            async with self.session.begin():
                document = await DocumentRepository(self.session).get_knowledge_for_update(
                    document_id
                )
                if document is not None:
                    document.status = DocumentStatus.FAILED.value
                    document.parsed_text_object_key = parsed_object_key
                    document.parsed_ir_object_key = parsed_ir_object_key
                    ingestion_error: dict[str, object] | None = None
                    if error is not None:
                        ingestion_error = {
                            "code": type(error).__name__,
                            "message": str(error)[:1500],
                        }
                        if isinstance(error, DuplicateKnowledgeError):
                            ingestion_error.update(
                                existing_document_id=error.document_id,
                                existing_title=error.title,
                            )
                    document.extra_data = {
                        **document.extra_data,
                        "ingestion_stage": "FAILED",
                        "ingestion_error": ingestion_error,
                        **(
                            {"chunks_object_key": chunks_object_key}
                            if chunks_object_key is not None
                            else {}
                        ),
                    }
                    return True
        except Exception:
            logger.exception(
                "knowledge_ingestion_failure_state_update_failed",
                document_id=document_id,
            )
        return False
