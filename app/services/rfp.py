from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import UploadFile
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    CustomerNotFoundError,
    ObjectStorageError,
    RFPConflictError,
    RFPNotFoundError,
    RFPRetryConflictError,
)
from app.models import RFP, Document, OutboxEvent, WorkflowRun
from app.models.enums import (
    DocumentStatus,
    DocumentType,
    OutboxStatus,
    RFPStatus,
    WorkflowRunType,
    WorkflowStatus,
)
from app.models.mixins import generate_uuid, utc_now
from app.repositories import (
    CapabilityResultRepository,
    CustomerRepository,
    DocumentRepository,
    OutboxEventRepository,
    RequirementRepository,
    RFPRepository,
    WorkflowRunRepository,
)
from app.services.outbox import EventDeliveryStatus, OutboxPublisher
from app.services.storage import ObjectStorageService

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CreateRFPCommand:
    customer_id: str
    title: str
    reference_number: str | None
    priority: str
    source_language: str | None
    due_at: datetime | None


@dataclass(frozen=True, slots=True)
class CreateRFPResult:
    rfp: RFP
    document: Document
    workflow_run: WorkflowRun
    event: OutboxEvent
    event_status: EventDeliveryStatus


@dataclass(frozen=True, slots=True)
class RetryRFPResult:
    rfp: RFP
    workflow_run: WorkflowRun
    retried_stage: str
    event: OutboxEvent
    event_status: EventDeliveryStatus
    queued_at: datetime


@dataclass(frozen=True, slots=True)
class RFPPage:
    items: list[RFP]
    total: int
    offset: int
    limit: int


class RFPService:
    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
        storage: ObjectStorageService,
        outbox_publisher: OutboxPublisher,
    ) -> None:
        self.settings = settings
        self.session = session
        self.storage = storage
        self.outbox_publisher = outbox_publisher

    async def create(self, command: CreateRFPCommand, upload: UploadFile) -> CreateRFPResult:
        async with self.session.begin():
            customer = await CustomerRepository(self.session).get_active(command.customer_id)
            if customer is None:
                raise CustomerNotFoundError(f"customer {command.customer_id} was not found")

        rfp_id = generate_uuid()
        document_id = generate_uuid()
        workflow_run_id = generate_uuid()
        event_id = generate_uuid()
        correlation_id = generate_uuid()

        stored_object = await self.storage.upload_rfp(
            upload,
            rfp_id=rfp_id,
            document_id=document_id,
        )

        queued_at = utc_now()
        rfp = RFP(
            id=rfp_id,
            customer_id=command.customer_id,
            title=command.title,
            reference_number=command.reference_number,
            status=RFPStatus.QUEUED.value,
            current_stage="queued",
            stage_started_at=queued_at,
            priority=command.priority,
            source_language=command.source_language,
            due_at=command.due_at,
        )
        document = Document(
            id=document_id,
            rfp_id=rfp_id,
            document_type=DocumentType.RFP_SOURCE.value,
            status=DocumentStatus.UPLOADED.value,
            bucket=stored_object.bucket,
            object_key=stored_object.object_key,
            original_filename=stored_object.original_filename,
            content_type=stored_object.content_type,
            size_bytes=stored_object.size_bytes,
            checksum_sha256=stored_object.checksum_sha256,
            extra_data={},
        )
        workflow_run = WorkflowRun(
            id=workflow_run_id,
            rfp_id=rfp_id,
            run_type=WorkflowRunType.FULL.value,
            status=WorkflowStatus.PENDING.value,
            current_node="parse_document",
            correlation_id=correlation_id,
            input_data={"document_id": document_id},
            output_summary={},
        )
        event = OutboxEvent(
            id=event_id,
            aggregate_type="RFP",
            aggregate_id=rfp_id,
            topic="rfp.uploaded",
            event_key=rfp_id,
            payload={
                "event_id": event_id,
                "event_type": "rfp.uploaded",
                "occurred_at": datetime.now(UTC).isoformat(),
                "rfp_id": rfp_id,
                "document_id": document_id,
                "workflow_run_id": workflow_run_id,
                "correlation_id": correlation_id,
            },
            status=OutboxStatus.PENDING.value,
        )

        try:
            async with self.session.begin():
                # Serialize against customer deletion, including uploads already in flight.
                customer = await CustomerRepository(self.session).get_active_for_update(
                    command.customer_id
                )
                if customer is None:
                    raise CustomerNotFoundError("客户不存在或已删除")
                RFPRepository(self.session).add(rfp)
                DocumentRepository(self.session).add(document)
                WorkflowRunRepository(self.session).add(workflow_run)
                OutboxEventRepository(self.session).add(event)
                await self.session.flush()
        except IntegrityError as exc:
            await self._remove_uploaded_object(stored_object.bucket, stored_object.object_key)
            raise RFPConflictError(
                "an RFP with the same customer reference already exists"
            ) from exc
        except Exception:
            await self._remove_uploaded_object(stored_object.bucket, stored_object.object_key)
            raise

        event_status = await self.outbox_publisher.publish_event(self.session, event)
        logger.info(
            "rfp_created",
            rfp_id=rfp.id,
            document_id=document.id,
            workflow_run_id=workflow_run.id,
            event_status=event_status,
        )
        return CreateRFPResult(
            rfp=rfp,
            document=document,
            workflow_run=workflow_run,
            event=event,
            event_status=event_status,
        )

    async def get(self, rfp_id: str) -> RFP:
        async with self.session.begin():
            rfp = await RFPRepository(self.session).get_detail(rfp_id)
        if rfp is None:
            raise RFPNotFoundError(f"RFP {rfp_id} was not found")
        return rfp

    async def list(
        self,
        *,
        offset: int,
        limit: int,
        customer_id: str | None,
        status: str | None,
        search: str | None,
    ) -> RFPPage:
        normalized_search = search.strip() if search else None
        repository = RFPRepository(self.session)
        async with self.session.begin():
            items = await repository.list_active(
                offset=offset,
                limit=limit,
                customer_id=customer_id,
                status=status,
                search=normalized_search,
            )
            total = await repository.count_active(
                customer_id=customer_id,
                status=status,
                search=normalized_search,
            )
        return RFPPage(items=items, total=total, offset=offset, limit=limit)

    async def delete(self, rfp_id: str) -> None:
        async with self.session.begin():
            rfp = await RFPRepository(self.session).get_active_for_update(rfp_id)
            if rfp is None:
                raise RFPNotFoundError("任务不存在或已删除")
            now = utc_now()
            rfp.deleted_at = now
            rfp.status = RFPStatus.ARCHIVED.value
            rfp.current_stage = "deleted"
            rfp.completed_at = now
            await self.session.execute(
                update(WorkflowRun)
                .where(
                    WorkflowRun.rfp_id == rfp_id,
                    WorkflowRun.status.in_(
                        [
                            WorkflowStatus.PENDING.value,
                            WorkflowStatus.RUNNING.value,
                            WorkflowStatus.WAITING_REVIEW.value,
                        ]
                    ),
                )
                .values(status=WorkflowStatus.CANCELLED.value, completed_at=now)
            )
            await self.session.execute(
                update(OutboxEvent)
                .where(
                    OutboxEvent.event_key == rfp_id,
                    OutboxEvent.status == OutboxStatus.PENDING.value,
                )
                .values(status=OutboxStatus.FAILED.value, last_error="RFP_DELETED")
            )

    async def retry(self, rfp_id: str) -> RetryRFPResult:
        event_id = generate_uuid()
        queued_at = utc_now()
        async with self.session.begin():
            rfp_repository = RFPRepository(self.session)
            rfp = await rfp_repository.get_active_for_update(rfp_id)
            if rfp is None:
                raise RFPNotFoundError(f"RFP {rfp_id} was not found")
            if rfp.status != RFPStatus.FAILED.value:
                raise RFPRetryConflictError("only a failed RFP can be retried")

            retried_stage = rfp.current_stage
            workflow_run = await WorkflowRunRepository(self.session).get_latest_for_rfp(rfp.id)
            document = await DocumentRepository(self.session).get_rfp_source(rfp.id)
            if workflow_run is None or document is None:
                raise RFPRetryConflictError("RFP workflow state is incomplete")
            if workflow_run.status != WorkflowStatus.FAILED.value:
                raise RFPRetryConflictError("workflow is not in a failed state")
            completion_flags = {
                "extract_requirements": "requirements_extracted",
                "evaluate_capabilities": "capabilities_evaluated",
                "generate_proposal": "proposal_generated",
            }
            completed_flag = completion_flags.get(retried_stage)
            if completed_flag and workflow_run.output_summary.get(completed_flag) is True:
                raise RFPRetryConflictError("failed stage already has committed results")
            if retried_stage == "parse_document" and document.status == DocumentStatus.READY.value:
                raise RFPRetryConflictError("source document has already been parsed")

            topic, payload = await self._retry_event(
                rfp=rfp,
                document=document,
                workflow_run=workflow_run,
                stage=retried_stage,
                event_id=event_id,
                queued_at=queued_at,
            )
            workflow_run.attempt += 1
            workflow_run.status = WorkflowStatus.PENDING.value
            workflow_run.current_node = {
                "parse_document": "parse_document",
                "extract_requirements": "analyst_agent",
                "evaluate_capabilities": "capability_agent",
                "generate_proposal": "proposal_agent",
            }[retried_stage]
            workflow_run.error_code = None
            workflow_run.error_message = None
            workflow_run.completed_at = None
            workflow_run.output_summary = {
                **workflow_run.output_summary,
                "last_retry_stage": retried_stage,
                "last_retry_at": queued_at.isoformat(),
            }
            rfp.status = RFPStatus.QUEUED.value
            rfp.error_message = None
            rfp.completed_at = None
            rfp.stage_started_at = queued_at

            event = OutboxEvent(
                id=event_id,
                aggregate_type="RFP",
                aggregate_id=rfp.id,
                topic=topic,
                event_key=rfp.id,
                payload=payload,
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(self.session).add(event)
            await self.session.flush()

        event_status = await self.outbox_publisher.publish_event(self.session, event)
        logger.info(
            "rfp_retry_queued",
            rfp_id=rfp.id,
            workflow_run_id=workflow_run.id,
            stage=retried_stage,
            attempt=workflow_run.attempt,
            event_status=event_status,
        )
        return RetryRFPResult(
            rfp=rfp,
            workflow_run=workflow_run,
            retried_stage=retried_stage,
            event=event,
            event_status=event_status,
            queued_at=queued_at,
        )

    async def _retry_event(
        self,
        *,
        rfp: RFP,
        document: Document,
        workflow_run: WorkflowRun,
        stage: str,
        event_id: str,
        queued_at: datetime,
    ) -> tuple[str, dict[str, object]]:
        common: dict[str, object] = {
            "event_id": event_id,
            "occurred_at": queued_at.replace(tzinfo=UTC).isoformat(),
            "rfp_id": rfp.id,
            "workflow_run_id": workflow_run.id,
        }
        if stage == "parse_document":
            return self.settings.kafka_rfp_topic, {
                **common,
                "event_type": "rfp.uploaded",
                "document_id": document.id,
                "correlation_id": workflow_run.correlation_id,
            }
        if stage == "extract_requirements":
            if not document.parsed_text_object_key:
                raise RFPRetryConflictError("parsed RFP text is unavailable")
            return self.settings.kafka_rfp_completed_topic, {
                **common,
                "event_type": "rfp.completed",
                "document_id": document.id,
                "parsed_text_object_key": document.parsed_text_object_key,
            }
        if stage == "evaluate_capabilities":
            requirement_count = await RequirementRepository(self.session).count_for_rfp(rfp.id)
            return self.settings.kafka_requirements_extracted_topic, {
                **common,
                "event_type": "rfp.requirements.extracted",
                "document_id": document.id,
                "requirement_count": requirement_count,
            }
        if stage == "generate_proposal":
            capabilities = await CapabilityResultRepository(self.session).list_for_rfp(rfp.id)
            return self.settings.kafka_capabilities_evaluated_topic, {
                **common,
                "event_type": "rfp.capabilities.evaluated",
                "capability_count": len(capabilities),
            }
        raise RFPRetryConflictError(f"stage {stage!r} cannot be retried")

    async def _remove_uploaded_object(self, bucket: str, object_key: str) -> None:
        try:
            await self.storage.remove(bucket, object_key)
        except ObjectStorageError:
            logger.exception("orphaned_object_cleanup_failed", bucket=bucket, object_key=object_key)
