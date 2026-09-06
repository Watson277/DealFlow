import asyncio
from contextlib import suppress
from typing import Any

import orjson
import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.exceptions import LockNotAcquiredError
from app.core.logging import configure_logging
from app.db.session import async_session_factory, close_database
from app.documents.parser import DocumentParser
from app.infrastructure.locking.redis import DistributedLockService
from app.infrastructure.storage.local_artifacts import LocalArtifactExporter
from app.infrastructure.storage.minio import ObjectStorageService
from app.rag.chunking import KnowledgeChunker
from app.rag.embedding import OpenAIEmbeddingService
from app.rag.vector_store import QdrantKnowledgeStore
from app.schemas.events import KnowledgeIngestionRequestedEvent
from app.services.knowledge import KnowledgeService

logger = structlog.get_logger(__name__)


class KnowledgeWorker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.consumer = AIOKafkaConsumer(
            self.settings.kafka_knowledge_ingestion_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_knowledge_worker_group,
            client_id="dealflow-knowledge-worker",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=orjson.loads,
        )
        self.locks = DistributedLockService(self.settings)
        self.storage = ObjectStorageService(self.settings)
        self.parser = DocumentParser.from_settings(self.settings)
        self.chunker = KnowledgeChunker(self.settings)
        self.embeddings = OpenAIEmbeddingService(self.settings)
        self.vector_store = QdrantKnowledgeStore(self.settings)
        self.local_exporter = LocalArtifactExporter(self.settings)
        self._stop_requested = asyncio.Event()
        self.started = asyncio.Event()

    async def run(self) -> None:
        await self.consumer.start()
        self.started.set()
        logger.info(
            "knowledge_worker_started",
            topic=self.settings.kafka_knowledge_ingestion_topic,
            group_id=self.settings.kafka_knowledge_worker_group,
        )
        try:
            while not self._stop_requested.is_set():
                try:
                    message: Any = await asyncio.wait_for(
                        self.consumer.getone(),
                        timeout=1.0,
                    )
                except TimeoutError:
                    continue

                try:
                    event = KnowledgeIngestionRequestedEvent.model_validate(message.value)
                except ValidationError:
                    logger.exception(
                        "invalid_knowledge_ingestion_event_discarded",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                    )
                    await self.consumer.commit()
                    continue

                try:
                    async with (
                        self.locks.lock(f"lock:knowledge:{event.document_id}"),
                        async_session_factory() as session,
                    ):
                        service = KnowledgeService(
                            session=session,
                            storage=self.storage,
                            parser=self.parser,
                            chunker=self.chunker,
                            embeddings=self.embeddings,
                            vector_store=self.vector_store,
                            local_exporter=self.local_exporter,
                        )
                        await service.process_queued_ingestion(event.document_id)
                except LockNotAcquiredError:
                    logger.warning(
                        "knowledge_ingestion_lock_busy",
                        document_id=event.document_id,
                    )
                    partition = TopicPartition(message.topic, message.partition)
                    self.consumer.seek(partition, message.offset)
                    await asyncio.sleep(1)
                    continue
                except Exception:
                    logger.exception(
                        "knowledge_ingestion_event_crashed",
                        document_id=event.document_id,
                    )
                    partition = TopicPartition(message.topic, message.partition)
                    self.consumer.seek(partition, message.offset)
                    await asyncio.sleep(1)
                    continue

                await self.consumer.commit()
        finally:
            await self.close()

    def request_stop(self) -> None:
        self._stop_requested.set()

    async def close(self) -> None:
        await self.consumer.stop()
        await self.locks.close()
        await self.vector_store.close()
        await close_database()
        logger.info("knowledge_worker_stopped")


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    worker = KnowledgeWorker(settings)
    await worker.run()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
