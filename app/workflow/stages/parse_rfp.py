import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import DocumentProcessingError
from app.db.session import async_session_factory
from app.infrastructure.locking.redis import DistributedLockService
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.infrastructure.storage.minio import ObjectStorageService
from app.models import RFP, Document, OutboxEvent, WorkflowRun
from app.models.enums import (
    DocumentStatus,
    OutboxStatus,
    RFPStatus,
    WorkflowStatus,
)
from app.models.mixins import generate_uuid, utc_now
from app.repositories import (
    DocumentRepository,
    OutboxEventRepository,
    RFPRepository,
    WorkflowRunRepository,
)
from app.schemas.events import RFPUploadedEvent
from app.services.document_parser import DocumentParser

logger = structlog.get_logger(__name__)


class RFPProcessingService:
    def __init__(
        self,
        settings: Settings,
        storage: ObjectStorageService,
        parser: DocumentParser,
        locks: DistributedLockService,
        outbox_publisher: OutboxPublisher,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.parser = parser
        self.locks = locks
        self.outbox_publisher = outbox_publisher

    async def process(self, event: RFPUploadedEvent) -> None:
        async with self.locks.lock(f"lock:rfp:{event.rfp_id}"):
            await self._process_locked(event)

    async def _process_locked(self, event: RFPUploadedEvent) -> None:
        async with async_session_factory() as session:
            try:
                entities = await self._mark_processing(session, event)
            except Exception as exc:
                await self._mark_failed(session, event, exc)
                logger.warning(
                    "rfp_processing_initialization_failed",
                    rfp_id=event.rfp_id,
                    error_type=type(exc).__name__,
                )
                return
            if entities is None:
                return
            rfp, document, workflow_run = entities

            parsed_object_key = f"rfp/{event.rfp_id}/parsed/{event.document_id}.txt"
            try:
                content = await self.storage.download(document.bucket, document.object_key)
                parsed = await asyncio.to_thread(
                    self.parser.parse,
                    content,
                    document.original_filename,
                )
                await self.storage.upload_text(parsed_object_key, parsed.text)
                completion_event = await self._mark_completed(
                    session,
                    event,
                    parsed_object_key=parsed_object_key,
                    page_count=parsed.page_count,
                    text_size=len(parsed.text.encode("utf-8")),
                )
            except Exception as exc:
                await self._mark_failed(session, event, exc)
                logger.warning(
                    "rfp_processing_failed",
                    rfp_id=event.rfp_id,
                    error_type=type(exc).__name__,
                )
                return

            await self.outbox_publisher.publish_event(session, completion_event)
            logger.info(
                "rfp_document_parsed",
                rfp_id=rfp.id,
                document_id=document.id,
                workflow_run_id=workflow_run.id,
                parsed_text_object_key=parsed_object_key,
            )

    async def _mark_processing(
        self,
        session: AsyncSession,
        event: RFPUploadedEvent,
    ) -> tuple[RFP, Document, WorkflowRun] | None:
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            document = await DocumentRepository(session).get(event.document_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)

            if rfp is None:
                logger.info("rfp_event_ignored_missing_rfp", rfp_id=event.rfp_id)
                return None
            if document is None or document.rfp_id != rfp.id:
                raise DocumentProcessingError("source document was not found for RFP")
            if workflow_run is None or workflow_run.rfp_id != rfp.id:
                raise DocumentProcessingError("workflow run was not found for RFP")
            if document.status == DocumentStatus.READY.value and document.parsed_text_object_key:
                logger.info("rfp_event_already_processed", rfp_id=rfp.id)
                return None

            now = utc_now()
            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "parse_document"
            rfp.stage_started_at = now
            rfp.processing_started_at = rfp.processing_started_at or now
            rfp.error_message = None
            document.status = DocumentStatus.PARSING.value
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "parse_document"
            workflow_run.started_at = workflow_run.started_at or now
            workflow_run.error_code = None
            workflow_run.error_message = None
        return rfp, document, workflow_run

    async def _mark_completed(
        self,
        session: AsyncSession,
        event: RFPUploadedEvent,
        *,
        parsed_object_key: str,
        page_count: int | None,
        text_size: int,
    ) -> OutboxEvent:
        completion_event_id = generate_uuid()
        now = utc_now()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            document = await DocumentRepository(session).get(event.document_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is None or document is None or workflow_run is None:
                raise DocumentProcessingError("RFP processing state disappeared")

            document.status = DocumentStatus.READY.value
            document.parsed_text_object_key = parsed_object_key
            document.page_count = page_count
            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "document_parsed"
            rfp.stage_started_at = now
            rfp.completed_at = None
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "analyst_agent"
            workflow_run.completed_at = None
            workflow_run.output_summary = {
                "parsed_text_object_key": parsed_object_key,
                "page_count": page_count,
                "text_size_bytes": text_size,
            }
            completion_event = OutboxEvent(
                id=completion_event_id,
                aggregate_type="RFP",
                aggregate_id=rfp.id,
                topic=self.settings.kafka_rfp_completed_topic,
                event_key=rfp.id,
                payload={
                    "event_id": completion_event_id,
                    "event_type": "rfp.completed",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": rfp.id,
                    "document_id": document.id,
                    "workflow_run_id": workflow_run.id,
                    "parsed_text_object_key": parsed_object_key,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(completion_event)
            await session.flush()
        return completion_event

    async def _mark_failed(
        self,
        session: AsyncSession,
        event: RFPUploadedEvent,
        error: Exception,
    ) -> None:
        now = utc_now()
        error_type = type(error).__name__
        error_message = f"{error_type}: {str(error)[:1500]}"
        failed_event_id = generate_uuid()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            if rfp is None:
                return  # Deleted tasks must not be revived by a late failure.
            document = await DocumentRepository(session).get(event.document_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)

            if rfp is not None:
                rfp.status = RFPStatus.FAILED.value
                rfp.current_stage = "parse_document"
                rfp.error_message = error_message
            if document is not None:
                document.status = DocumentStatus.FAILED.value
            if workflow_run is not None:
                workflow_run.status = WorkflowStatus.FAILED.value
                workflow_run.current_node = "parse_document"
                workflow_run.error_code = error_type
                workflow_run.error_message = error_message
                workflow_run.completed_at = now

            failed_event = OutboxEvent(
                id=failed_event_id,
                aggregate_type="RFP",
                aggregate_id=event.rfp_id,
                topic=self.settings.kafka_rfp_failed_topic,
                event_key=event.rfp_id,
                payload={
                    "event_id": failed_event_id,
                    "event_type": "rfp.failed",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": event.rfp_id,
                    "document_id": event.document_id,
                    "workflow_run_id": event.workflow_run_id,
                    "error_code": error_type,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(failed_event)
            await session.flush()
        await self.outbox_publisher.publish_event(session, failed_event)
