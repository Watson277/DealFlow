import asyncio
from contextlib import suppress
from typing import Any

import orjson
import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.agents.capability_judge import CapabilityJudge, OpenAICapabilityJudge
from app.core.config import Settings, get_settings
from app.core.exceptions import LockNotAcquiredError
from app.core.logging import configure_logging
from app.db.session import close_database
from app.infrastructure.locking.redis import DistributedLockService
from app.infrastructure.messaging.consumed_events import ConsumedEventTracker
from app.infrastructure.messaging.kafka import KafkaProducerService
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.rag.embedding import EmbeddingService, OpenAIEmbeddingService
from app.rag.reranker import CrossEncoderEvidenceReranker, EvidenceReranker
from app.rag.vector_store import QdrantKnowledgeStore
from app.schemas.events import RequirementsExtractedEvent
from app.workflow.stages.evaluate_capabilities import CapabilityProcessingService

logger = structlog.get_logger(__name__)


class CapabilityWorker:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        embeddings: EmbeddingService | None = None,
        judge: CapabilityJudge | None = None,
        vector_store: QdrantKnowledgeStore | None = None,
        reranker: EvidenceReranker | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.consumer = AIOKafkaConsumer(
            self.settings.kafka_requirements_extracted_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_capability_worker_group,
            client_id="dealflow-capability-worker",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=orjson.loads,
        )
        self.kafka = KafkaProducerService(self.settings)
        self.consumed_events = ConsumedEventTracker(
            self.settings.kafka_capability_worker_group
        )
        self.locks = DistributedLockService(self.settings)
        self.vector_store = vector_store or QdrantKnowledgeStore(self.settings)
        self.processor = CapabilityProcessingService(
            settings=self.settings,
            embeddings=embeddings or OpenAIEmbeddingService(self.settings),
            vector_store=self.vector_store,
            judge=judge or OpenAICapabilityJudge(self.settings),
            locks=self.locks,
            outbox_publisher=OutboxPublisher(self.kafka),
            reranker=reranker or CrossEncoderEvidenceReranker(self.settings),
        )
        self._stop_requested = asyncio.Event()
        self.started = asyncio.Event()

    async def run(self) -> None:
        await self.consumer.start()
        self.started.set()
        logger.info(
            "capability_worker_started",
            topic=self.settings.kafka_requirements_extracted_topic,
            group_id=self.settings.kafka_capability_worker_group,
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
                    event = RequirementsExtractedEvent.model_validate(message.value)
                except ValidationError:
                    logger.exception(
                        "invalid_capability_event_discarded",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                    )
                    await self.consumer.commit()
                    continue

                try:
                    if await self.consumed_events.is_consumed(event.event_id):
                        logger.info(
                            "capability_duplicate_event_skipped",
                            event_id=event.event_id,
                            rfp_id=event.rfp_id,
                        )
                    else:
                        await self.processor.process(event)
                        await self.consumed_events.record(
                            event_id=event.event_id,
                            event_type=event.event_type,
                            topic=message.topic,
                            partition=message.partition,
                            offset=message.offset,
                        )
                except LockNotAcquiredError:
                    logger.warning("capability_lock_busy", rfp_id=event.rfp_id)
                    partition = TopicPartition(message.topic, message.partition)
                    self.consumer.seek(partition, message.offset)
                    await asyncio.sleep(1)
                    continue
                except Exception:
                    logger.exception("capability_event_processing_crashed", rfp_id=event.rfp_id)
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
        await self.kafka.stop()
        await self.locks.close()
        await self.vector_store.close()
        await close_database()
        logger.info("capability_worker_stopped")


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    worker = CapabilityWorker(settings)
    await worker.run()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
