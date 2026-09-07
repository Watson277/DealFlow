import asyncio
from contextlib import suppress
from typing import Any

import orjson
import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.agents.requirement_extractor import OpenAIRequirementExtractor, RequirementExtractor
from app.core.config import Settings, get_settings
from app.core.exceptions import LockNotAcquiredError
from app.core.logging import configure_logging
from app.db.session import close_database
from app.infrastructure.locking.redis import DistributedLockService
from app.infrastructure.messaging.consumed_events import ConsumedEventTracker
from app.infrastructure.messaging.kafka import KafkaProducerService
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.infrastructure.storage.minio import ObjectStorageService
from app.schemas.events import RFPCompletedEvent
from app.workflow.stages.extract_requirements import RequirementProcessingService

logger = structlog.get_logger(__name__)


class RequirementWorker:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        extractor: RequirementExtractor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.consumer = AIOKafkaConsumer(
            self.settings.kafka_rfp_completed_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_requirement_worker_group,
            client_id="dealflow-requirement-worker",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=orjson.loads,
        )
        self.kafka = KafkaProducerService(self.settings)
        self.consumed_events = ConsumedEventTracker(
            self.settings.kafka_requirement_worker_group
        )
        self.locks = DistributedLockService(self.settings)
        self.processor = RequirementProcessingService(
            settings=self.settings,
            storage=ObjectStorageService(self.settings),
            extractor=extractor or OpenAIRequirementExtractor(self.settings),
            locks=self.locks,
            outbox_publisher=OutboxPublisher(self.kafka),
        )
        self._stop_requested = asyncio.Event()
        self.started = asyncio.Event()

    async def run(self) -> None:
        await self.consumer.start()
        self.started.set()
        logger.info(
            "requirement_worker_started",
            topic=self.settings.kafka_rfp_completed_topic,
            group_id=self.settings.kafka_requirement_worker_group,
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
                    event = RFPCompletedEvent.model_validate(message.value)
                except ValidationError:
                    logger.exception(
                        "invalid_requirement_event_discarded",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                    )
                    await self.consumer.commit()
                    continue

                try:
                    if await self.consumed_events.is_consumed(event.event_id):
                        logger.info(
                            "requirement_duplicate_event_skipped",
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
                    logger.warning("requirement_lock_busy", rfp_id=event.rfp_id)
                    partition = TopicPartition(message.topic, message.partition)
                    self.consumer.seek(partition, message.offset)
                    await asyncio.sleep(1)
                    continue
                except Exception:
                    logger.exception("requirement_event_processing_crashed", rfp_id=event.rfp_id)
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
        await close_database()
        logger.info("requirement_worker_stopped")


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    worker = RequirementWorker(settings)
    await worker.run()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
