import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.requirement_extractor import RequirementExtractor
from app.core.config import Settings
from app.core.exceptions import RequirementExtractionError
from app.db.session import async_session_factory
from app.models import RFP, Document, OutboxEvent, Requirement, WorkflowRun
from app.models.enums import OutboxStatus, RFPStatus, WorkflowStatus
from app.models.mixins import generate_uuid, utc_now
from app.repositories import (
    DocumentRepository,
    OutboxEventRepository,
    RequirementRepository,
    RFPRepository,
    WorkflowRunRepository,
)
from app.schemas.events import RFPCompletedEvent
from app.schemas.requirement import ExtractedRequirement
from app.services.lock import DistributedLockService
from app.services.outbox import OutboxPublisher
from app.services.storage import ObjectStorageService

logger = structlog.get_logger(__name__)


class RequirementProcessingService:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: ObjectStorageService,
        extractor: RequirementExtractor,
        locks: DistributedLockService,
        outbox_publisher: OutboxPublisher,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.extractor = extractor
        self.locks = locks
        self.outbox_publisher = outbox_publisher

    async def process(self, event: RFPCompletedEvent) -> None:
        async with self.locks.lock(
            f"lock:requirements:{event.rfp_id}",
            ttl_seconds=self.settings.requirement_lock_ttl_seconds,
        ):
            await self._process_locked(event)

    async def _process_locked(self, event: RFPCompletedEvent) -> None:
        async with async_session_factory() as session:
            try:
                entities = await self._mark_extracting(session, event)
            except Exception as exc:
                await self._mark_failed(session, event, exc)
                return
            if entities is None:
                return
            rfp, document, workflow_run = entities

            try:
                parsed_text = (
                    await self.storage.download(document.bucket, event.parsed_text_object_key)
                ).decode("utf-8")
                extracted = await self.extractor.extract(
                    parsed_text,
                    rfp_id=rfp.id,
                    title=rfp.title,
                )
                completion_event = await self._save_requirements(
                    session,
                    event,
                    extracted,
                )
            except Exception as exc:
                await self._mark_failed(session, event, exc)
                logger.warning(
                    "requirement_extraction_failed",
                    rfp_id=event.rfp_id,
                    error_type=type(exc).__name__,
                )
                return

            await self.outbox_publisher.publish_event(session, completion_event)
            logger.info(
                "requirements_extracted",
                rfp_id=rfp.id,
                document_id=document.id,
                workflow_run_id=workflow_run.id,
                requirement_count=completion_event.payload["requirement_count"],
            )

    async def _mark_extracting(
        self,
        session: AsyncSession,
        event: RFPCompletedEvent,
    ) -> tuple[RFP, Document, WorkflowRun] | None:
        now = utc_now()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            document = await DocumentRepository(session).get(event.document_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is None:
                logger.info("requirement_event_ignored_missing_rfp", rfp_id=event.rfp_id)
                return None
            if document is None or document.rfp_id != rfp.id:
                raise RequirementExtractionError("parsed source document was not found")
            if document.parsed_text_object_key != event.parsed_text_object_key:
                raise RequirementExtractionError("parsed document object key does not match")
            if workflow_run is None or workflow_run.rfp_id != rfp.id:
                raise RequirementExtractionError("workflow run was not found for RFP")

            if (
                rfp.current_stage == "requirements_extracted"
                or workflow_run.output_summary.get("requirements_extracted") is True
            ):
                logger.info("requirement_event_already_processed", rfp_id=rfp.id)
                return None

            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "extract_requirements"
            rfp.stage_started_at = now
            rfp.error_message = None
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "analyst_agent"
            workflow_run.error_code = None
            workflow_run.error_message = None
        return rfp, document, workflow_run

    async def _save_requirements(
        self,
        session: AsyncSession,
        event: RFPCompletedEvent,
        extracted: list[ExtractedRequirement],
    ) -> OutboxEvent:
        requirements = self._deduplicate(extracted)
        completion_event_id = generate_uuid()
        now = utc_now()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            document = await DocumentRepository(session).get(event.document_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is None or document is None or workflow_run is None:
                raise RequirementExtractionError("RFP extraction state disappeared")

            repository = RequirementRepository(session)
            for index, item in enumerate(requirements, start=1):
                normalized_text = self._normalize_text(item.normalized_text)
                fingerprint = hashlib.sha256(normalized_text.casefold().encode()).hexdigest()
                repository.add(
                    Requirement(
                        id=generate_uuid(),
                        rfp_id=rfp.id,
                        source_document_id=document.id,
                        requirement_key=f"REQ-{index:04d}",
                        category=item.category.strip().lower(),
                        requirement_text=item.requirement_text.strip(),
                        normalized_text=normalized_text,
                        mandatory=item.mandatory,
                        source_page_start=item.source_page_start,
                        source_page_end=item.source_page_end,
                        source_quote=item.source_quote.strip() if item.source_quote else None,
                        confidence=Decimal(str(round(item.confidence, 4))),
                        fingerprint=fingerprint,
                        raw_output=item.model_dump(mode="json"),
                    )
                )

            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "requirements_extracted"
            rfp.stage_started_at = now
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "capability_agent"
            workflow_run.output_summary = {
                **workflow_run.output_summary,
                "requirement_count": len(requirements),
                "requirements_extracted": True,
            }
            completion_event = OutboxEvent(
                id=completion_event_id,
                aggregate_type="RFP",
                aggregate_id=rfp.id,
                topic=self.settings.kafka_requirements_extracted_topic,
                event_key=rfp.id,
                payload={
                    "event_id": completion_event_id,
                    "event_type": "rfp.requirements.extracted",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": rfp.id,
                    "document_id": document.id,
                    "workflow_run_id": workflow_run.id,
                    "requirement_count": len(requirements),
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(completion_event)
            await session.flush()
        return completion_event

    async def _mark_failed(
        self,
        session: AsyncSession,
        event: RFPCompletedEvent,
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
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is not None:
                rfp.status = RFPStatus.FAILED.value
                rfp.current_stage = "extract_requirements"
                rfp.error_message = error_message
            if workflow_run is not None:
                workflow_run.status = WorkflowStatus.FAILED.value
                workflow_run.current_node = "analyst_agent"
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
                    "stage": "analyst_agent",
                    "error_code": error_type,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(failed_event)
            await session.flush()
        await self.outbox_publisher.publish_event(session, failed_event)

    @classmethod
    def _deduplicate(
        cls,
        extracted: list[ExtractedRequirement],
    ) -> list[ExtractedRequirement]:
        unique: dict[str, ExtractedRequirement] = {}
        for item in extracted:
            key = cls._normalize_text(item.normalized_text).casefold()
            previous = unique.get(key)
            if previous is None or item.confidence > previous.confidence:
                unique[key] = item
        return list(unique.values())

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.split())
