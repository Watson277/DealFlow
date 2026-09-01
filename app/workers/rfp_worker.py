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
from app.db.session import close_database
from app.documents.parser import DocumentParser
from app.infrastructure.locking.redis import DistributedLockService
from app.infrastructure.messaging.kafka import KafkaProducerService
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.infrastructure.storage.minio import ObjectStorageService
from app.schemas.events import RFPUploadedEvent
from app.workflow.stages.parse_rfp import RFPProcessingService

logger = structlog.get_logger(__name__)


class RFPWorker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.consumer = AIOKafkaConsumer(
            self.settings.kafka_rfp_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_rfp_worker_group,
            client_id="dealflow-rfp-worker",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=orjson.loads,
        )
        self.kafka = KafkaProducerService(self.settings)
        self.locks = DistributedLockService(self.settings)
        self.processor = RFPProcessingService(
            settings=self.settings,
            storage=ObjectStorageService(self.settings),
            parser=DocumentParser(),
            locks=self.locks,
            outbox_publisher=OutboxPublisher(self.kafka),
        )
        self._stop_requested = asyncio.Event()
        self.started = asyncio.Event()

    async def run(self) -> None:
        await self.consumer.start()
        self.started.set()
        logger.info(
            "rfp_worker_started",
            topic=self.settings.kafka_rfp_topic,
            group_id=self.settings.kafka_rfp_worker_group,
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
                    event = RFPUploadedEvent.model_validate(message.value)
                except ValidationError:
                    logger.exception(
                        "invalid_rfp_event_discarded",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                    )
                    await self.consumer.commit()
                    continue

                try:
                    await self.processor.process(event)
                except LockNotAcquiredError:
                    logger.warning("rfp_lock_busy", rfp_id=event.rfp_id)
                    partition = TopicPartition(message.topic, message.partition)
                    self.consumer.seek(partition, message.offset)
                    await asyncio.sleep(1)
                    continue
                except Exception:
                    logger.exception("rfp_event_processing_crashed", rfp_id=event.rfp_id)
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
        logger.info("rfp_worker_stopped")


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    worker = RFPWorker(settings)
    await worker.run()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
