import asyncio
import os
import signal
import socket
from contextlib import suppress
from typing import Any

import orjson
import structlog
from aiokafka import (  # type: ignore[import-untyped]
    AIOKafkaConsumer,
    ConsumerRebalanceListener,
    TopicPartition,
)
from aiokafka.errors import CommitFailedError  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.agents.requirement_extractor import OpenAIRequirementExtractor, RequirementExtractor
from app.core.config import Settings, get_settings
from app.core.exceptions import LockNotAcquiredError, LockOwnershipLostError
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


class RequirementWorker(ConsumerRebalanceListener):  # type: ignore[misc]
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        extractor: RequirementExtractor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.worker_id = (
            f"requirement-{socket.gethostname()}-"
            f"{os.environ.get('REQUIREMENT_WORKER_SLOT', '1')}-{os.getpid()}"
        )
        self.consumer = AIOKafkaConsumer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_requirement_worker_group,
            client_id=self.worker_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=orjson.loads,
            # Extraction budget + 60s for persistence + 60s for polling/cleanup.
            max_poll_interval_ms=int(
                (self.settings.requirement_worker_task_timeout_seconds + 120) * 1000
            ),
        )
        self.consumer.subscribe([self.settings.kafka_rfp_completed_topic], listener=self)
        self.kafka = KafkaProducerService(
            self.settings.model_copy(update={"kafka_client_id": self.worker_id})
        )
        self.consumed_events = ConsumedEventTracker(self.settings.kafka_requirement_worker_group)
        self.locks = DistributedLockService(self.settings)
        self._owned_extractor = (
            OpenAIRequirementExtractor(self.settings) if extractor is None else None
        )
        effective_extractor = extractor if extractor is not None else self._owned_extractor
        assert effective_extractor is not None
        self.processor = RequirementProcessingService(
            settings=self.settings,
            storage=ObjectStorageService(self.settings),
            extractor=effective_extractor,
            locks=self.locks,
            outbox_publisher=OutboxPublisher(self.kafka),
        )
        self._stop_requested = asyncio.Event()
        self.started = asyncio.Event()
        self._assigned: set[TopicPartition] = set()
        self._assignment_epoch = 0
        self._active_partition: TopicPartition | None = None
        self._active_task: asyncio.Task[None] | None = None

    async def on_partitions_revoked(self, revoked: set[TopicPartition]) -> None:
        self._assignment_epoch += 1
        self._assigned.difference_update(revoked)
        if self._active_partition in revoked and self._active_task is not None:
            self._active_task.cancel()
        # Do not await business work here: the Kafka coordinator needs this callback
        # to return. The main loop awaits cancellation and lock/transaction cleanup.
        logger.info(
            "requirement_partitions_revoked", partitions=sorted(p.partition for p in revoked)
        )

    async def on_partitions_assigned(self, assigned: set[TopicPartition]) -> None:
        self._assigned = set(assigned)
        logger.info(
            "requirement_partitions_assigned", partitions=sorted(p.partition for p in assigned)
        )

    def _owns(self, partition: TopicPartition, epoch: int) -> bool:
        return epoch == self._assignment_epoch and partition in self._assigned

    async def run(self) -> None:
        structlog.contextvars.bind_contextvars(worker_id=self.worker_id, pid=os.getpid())
        try:
            async with asyncio.timeout(60):
                await self.consumer.start()
            self.started.set()
            logger.info(
                "requirement_worker_started",
                topic=self.settings.kafka_rfp_completed_topic,
                group_id=self.settings.kafka_requirement_worker_group,
            )
            partitions = self.consumer.partitions_for_topic(self.settings.kafka_rfp_completed_topic)
            if partitions and self.settings.requirement_worker_processes > len(partitions):
                logger.warning(
                    "requirement_workers_exceed_partitions",
                    processes=self.settings.requirement_worker_processes,
                    partitions=len(partitions),
                )
            while not self._stop_requested.is_set():
                try:
                    message: Any = await asyncio.wait_for(
                        self.consumer.getone(),
                        timeout=1.0,
                    )
                except TimeoutError:
                    continue

                if self._stop_requested.is_set():
                    break  # Fetched but not processed; leave its offset uncommitted.
                partition = TopicPartition(message.topic, message.partition)
                epoch = self._assignment_epoch
                if not self._owns(partition, epoch):
                    continue
                self._active_partition = partition
                self._active_task = asyncio.create_task(
                    self._handle_message(message, partition, epoch),
                    name=f"requirement:{message.partition}:{message.offset}",
                )
                try:
                    async with asyncio.timeout(
                        self.settings.requirement_worker_task_timeout_seconds + 60
                    ):
                        await self._active_task
                except asyncio.CancelledError:
                    current = asyncio.current_task()
                    if current is not None and current.cancelling():
                        raise  # Shutdown cancellation, not just a revoked partition.
                    logger.info("requirement_work_cancelled_on_rebalance")
                except TimeoutError:
                    # Persistence/cleanup itself stalled. Restart this consumer;
                    # replay and business-state checks recover a committed result.
                    logger.error("requirement_worker_task_timed_out")
                    raise
                finally:
                    self._active_task = None
                    self._active_partition = None
        finally:
            await self.close()

    async def _handle_message(self, message: Any, partition: TopicPartition, epoch: int) -> None:
        with structlog.contextvars.bound_contextvars(
            topic=message.topic, partition=message.partition, offset=message.offset
        ):
            try:
                event = RFPCompletedEvent.model_validate(message.value)
            except ValidationError:
                logger.warning("invalid_requirement_event_discarded")
                await self._commit(message, partition, epoch)
                return
            with structlog.contextvars.bound_contextvars(rfp_id=event.rfp_id):
                try:
                    if not self._owns(partition, epoch):
                        return
                    if await self.consumed_events.is_consumed(event.event_id):
                        logger.info("requirement_duplicate_event_skipped", event_id=event.event_id)
                    else:
                        await self.processor.process(event)
                        if not self._owns(partition, epoch):
                            return
                        await self.consumed_events.record(
                            event_id=event.event_id,
                            event_type=event.event_type,
                            topic=message.topic,
                            partition=message.partition,
                            offset=message.offset,
                        )
                    await self._commit(message, partition, epoch)
                    return
                except (LockNotAcquiredError, LockOwnershipLostError) as exc:
                    logger.warning("requirement_lock_retry", error_type=type(exc).__name__)
                except Exception:
                    logger.exception("requirement_event_processing_crashed")
                if self._owns(partition, epoch):
                    self.consumer.seek(partition, message.offset)
                    with suppress(TimeoutError):
                        await asyncio.wait_for(self._stop_requested.wait(), timeout=1)

    async def _commit(self, message: Any, partition: TopicPartition, epoch: int) -> None:
        if not self._owns(partition, epoch):
            return
        try:
            await self.consumer.commit({partition: message.offset + 1})
        except CommitFailedError:
            # Rebalance won the race. Do not seek a revoked partition or commit
            # another generation's position; redelivery is safe via idempotency.
            logger.warning("requirement_commit_lost_assignment")

    def request_stop(self) -> None:
        self._stop_requested.set()

    async def close(self) -> None:
        closers = [self.consumer.stop(), self.kafka.stop(), self.locks.close(), close_database()]
        if self._owned_extractor is not None:
            closers.append(self._owned_extractor.aclose())
        try:
            async with asyncio.timeout(10):
                results = await asyncio.gather(*closers, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    logger.warning(
                        "requirement_worker_close_failed", error_type=type(result).__name__
                    )
        except TimeoutError:
            logger.warning("requirement_worker_close_timed_out")
        logger.info("requirement_worker_stopped")


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    structlog.configure(logger_factory=structlog.WriteLoggerFactory())
    worker = RequirementWorker(settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # signal.signal also works for local Windows development.
        signal.signal(sig, lambda _signum, _frame: loop.call_soon_threadsafe(worker.request_stop))
    await run_until_stopped(worker)


async def run_until_stopped(worker: RequirementWorker) -> None:
    task = asyncio.create_task(worker.run())

    async def drain() -> None:
        await worker._stop_requested.wait()
        logger.info("requirement_worker_draining", worker_id=worker.worker_id)
        await asyncio.sleep(worker.settings.requirement_worker_shutdown_timeout_seconds)
        logger.warning("requirement_worker_drain_expired", worker_id=worker.worker_id)
        task.cancel()

    drain_task = asyncio.create_task(drain())
    try:
        await task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if not worker._stop_requested.is_set() or (current is not None and current.cancelling()):
            raise
    finally:
        drain_task.cancel()
        with suppress(asyncio.CancelledError):
            await drain_task


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
