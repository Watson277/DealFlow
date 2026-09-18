from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.proposal_generator import ProposalContext, ProposalGenerator
from app.core.config import Settings
from app.core.exceptions import ProposalGenerationError
from app.db.session import async_session_factory
from app.infrastructure.locking.redis import DistributedLockService
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.infrastructure.storage.minio import ObjectStorageService
from app.models import RFP, CapabilityResult, Customer, OutboxEvent, Proposal, WorkflowRun
from app.models.enums import OutboxStatus, ProposalStatus, RFPStatus, WorkflowStatus
from app.models.mixins import generate_uuid, utc_now
from app.proposals.markdown_renderer import ProposalMarkdownRenderer
from app.repositories import (
    CapabilityResultRepository,
    CustomerRepository,
    OutboxEventRepository,
    ProposalRepository,
    RFPRepository,
    WorkflowRunRepository,
)
from app.schemas.events import CapabilitiesEvaluatedEvent
from app.schemas.proposal import ProposalDraft

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProposalInputs:
    rfp: RFP
    customer: Customer
    workflow_run: WorkflowRun
    capabilities: list[CapabilityResult]
    version: int


class ProposalProcessingService:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: ObjectStorageService,
        generator: ProposalGenerator,
        renderer: ProposalMarkdownRenderer,
        locks: DistributedLockService,
        outbox_publisher: OutboxPublisher,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.generator = generator
        self.renderer = renderer
        self.locks = locks
        self.outbox_publisher = outbox_publisher

    async def process(self, event: CapabilitiesEvaluatedEvent) -> None:
        async with self.locks.lock(
            f"lock:proposal:{event.rfp_id}",
            ttl_seconds=self.settings.proposal_lock_ttl_seconds,
        ):
            await self._process_locked(event)

    async def _process_locked(self, event: CapabilitiesEvaluatedEvent) -> None:
        async with async_session_factory() as session:
            try:
                inputs = await self._mark_generating(session, event)
            except Exception as exc:
                await self._mark_failed(session, event, exc)
                return
            if inputs is None:
                return

            proposal_id = generate_uuid()
            markdown_object_key = f"proposal/{event.rfp_id}/v{inputs.version}/{proposal_id}.md"
            try:
                context = self._build_context(inputs)
                draft = await self.generator.generate(context)
                self._validate_and_normalize_draft(draft, inputs.capabilities)
                markdown = self.renderer.render(draft)
                await self.storage.upload_text(
                    markdown_object_key,
                    markdown,
                    content_type="text/markdown; charset=utf-8",
                )
                proposal, completion_event = await self._save_proposal(
                    session,
                    event,
                    proposal_id=proposal_id,
                    version=inputs.version,
                    markdown_object_key=markdown_object_key,
                    draft=draft,
                )
            except Exception as exc:
                with suppress(Exception):
                    await self.storage.remove(self.settings.minio_bucket, markdown_object_key)
                await self._mark_failed(session, event, exc)
                logger.warning(
                    "proposal_generation_failed",
                    rfp_id=event.rfp_id,
                    error_type=type(exc).__name__,
                )
                return

            await self.outbox_publisher.publish_event(session, completion_event)
            logger.info(
                "proposal_generated",
                rfp_id=event.rfp_id,
                proposal_id=proposal.id,
                version=proposal.version,
            )

    async def _mark_generating(
        self,
        session: AsyncSession,
        event: CapabilitiesEvaluatedEvent,
    ) -> ProposalInputs | None:
        now = utc_now()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is None:
                logger.info("proposal_event_ignored_missing_rfp", rfp_id=event.rfp_id)
                return None
            if workflow_run is None or workflow_run.rfp_id != rfp.id:
                raise ProposalGenerationError("workflow run was not found for RFP")
            existing = await ProposalRepository(session).get_for_workflow(workflow_run.id)
            if (
                existing is not None
                and existing.status
                in {ProposalStatus.REVIEW_PENDING.value, ProposalStatus.APPROVED.value}
            ) or workflow_run.output_summary.get("proposal_generated") is True:
                logger.info("proposal_event_already_processed", rfp_id=rfp.id)
                return None
            customer = await CustomerRepository(session).get_active(rfp.customer_id)
            if customer is None:
                raise ProposalGenerationError("customer was not found for RFP")
            capabilities = await CapabilityResultRepository(session).list_for_rfp(rfp.id)
            if len(capabilities) != event.capability_count:
                raise ProposalGenerationError(
                    "persisted capability count does not match capability event"
                )
            version = await ProposalRepository(session).next_version(rfp.id)

            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "generate_proposal"
            rfp.stage_started_at = now
            rfp.error_message = None
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "proposal_agent"
            workflow_run.error_code = None
            workflow_run.error_message = None
        return ProposalInputs(
            rfp=rfp,
            customer=customer,
            workflow_run=workflow_run,
            capabilities=capabilities,
            version=version,
        )

    def _build_context(self, inputs: ProposalInputs) -> ProposalContext:
        capabilities: list[dict[str, object]] = []
        for result in inputs.capabilities:
            evidence = [
                {
                    "point_id": item.qdrant_point_id,
                    "document_title": item.document.extra_data.get("title")
                    or item.document.original_filename,
                    "document_version": item.document.document_version,
                    "page": item.page_number,
                    "snippet": item.snippet[: self.settings.proposal_evidence_max_chars],
                    "retrieval_score": (
                        float(item.retrieval_score) if item.retrieval_score is not None else None
                    ),
                }
                for item in sorted(
                    [item for item in result.evidence_items if item.is_selected]
                    or result.evidence_items,
                    key=lambda evidence_item: (
                        evidence_item.selection_order or evidence_item.rank_position
                    ),
                )[:3]
            ]
            capabilities.append(
                {
                    "requirement_key": result.requirement.requirement_key,
                    "requirement": result.requirement.requirement_text,
                    "normalized_requirement": result.requirement.normalized_text,
                    "category": result.requirement.category,
                    "mandatory": result.requirement.mandatory,
                    "capability_status": result.status,
                    "confidence": (
                        float(result.confidence) if result.confidence is not None else None
                    ),
                    "reason": result.reason,
                    "customization_notes": result.customization_notes,
                    "evidence": evidence,
                }
            )
        return ProposalContext(
            rfp={
                "id": inputs.rfp.id,
                "title": inputs.rfp.title,
                "reference_number": inputs.rfp.reference_number,
                "source_language": inputs.rfp.source_language,
                "due_at": inputs.rfp.due_at.isoformat() if inputs.rfp.due_at else None,
                "review_feedback": inputs.workflow_run.output_summary.get(
                    "proposal_review_comment"
                ),
                "previous_review_decision": inputs.workflow_run.output_summary.get(
                    "proposal_review_decision"
                ),
            },
            customer={
                "id": inputs.customer.id,
                "name": inputs.customer.name,
                "industry": inputs.customer.industry,
                "website": inputs.customer.website,
            },
            capabilities=capabilities,
        )

    @staticmethod
    def _validate_and_normalize_draft(
        draft: ProposalDraft,
        capabilities: list[CapabilityResult],
    ) -> None:
        expected = {result.requirement.requirement_key: result for result in capabilities}
        actual_keys = [item.requirement_key for item in draft.requirement_responses]
        if len(actual_keys) != len(set(actual_keys)) or set(actual_keys) != set(expected):
            raise ProposalGenerationError(
                "proposal response matrix must contain every requirement exactly once"
            )
        for item in draft.requirement_responses:
            result = expected[item.requirement_key]
            item.requirement = result.requirement.requirement_text
            item.capability_status = type(item.capability_status)(result.status)

    async def _save_proposal(
        self,
        session: AsyncSession,
        event: CapabilitiesEvaluatedEvent,
        *,
        proposal_id: str,
        version: int,
        markdown_object_key: str,
        draft: ProposalDraft,
    ) -> tuple[Proposal, OutboxEvent]:
        event_id = generate_uuid()
        now = utc_now()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is None or workflow_run is None:
                raise ProposalGenerationError("RFP proposal state disappeared")
            proposal = Proposal(
                id=proposal_id,
                rfp_id=rfp.id,
                workflow_run_id=workflow_run.id,
                version=version,
                status=ProposalStatus.REVIEW_PENDING.value,
                title=draft.title.strip(),
                executive_summary=draft.executive_summary.strip(),
                markdown_object_key=markdown_object_key,
                model_name=self.settings.llm_model,
                prompt_version=self.settings.proposal_prompt_version,
                content=draft.model_dump(mode="json"),
            )
            ProposalRepository(session).add(proposal)
            rfp.status = RFPStatus.REVIEW_PENDING.value
            rfp.current_stage = "human_review"
            rfp.stage_started_at = now
            workflow_run.status = WorkflowStatus.WAITING_REVIEW.value
            workflow_run.current_node = "human_review"
            workflow_run.output_summary = {
                **workflow_run.output_summary,
                "proposal_generated": True,
                "proposal_id": proposal_id,
                "proposal_version": version,
            }
            completion_event = OutboxEvent(
                id=event_id,
                aggregate_type="Proposal",
                aggregate_id=proposal_id,
                topic=self.settings.kafka_proposal_generated_topic,
                event_key=rfp.id,
                payload={
                    "event_id": event_id,
                    "event_type": "proposal.generated",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": rfp.id,
                    "workflow_run_id": workflow_run.id,
                    "proposal_id": proposal_id,
                    "version": version,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(completion_event)
            await session.flush()
        return proposal, completion_event

    async def _mark_failed(
        self,
        session: AsyncSession,
        event: CapabilitiesEvaluatedEvent,
        error: Exception,
    ) -> None:
        now = utc_now()
        error_type = type(error).__name__
        error_message = f"{error_type}: {str(error)[:1500]}"
        event_id = generate_uuid()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            if rfp is None:
                return  # Deleted tasks must not be revived by a late failure.
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is not None:
                rfp.status = RFPStatus.FAILED.value
                rfp.current_stage = "generate_proposal"
                rfp.error_message = error_message
            if workflow_run is not None:
                workflow_run.status = WorkflowStatus.FAILED.value
                workflow_run.current_node = "proposal_agent"
                workflow_run.error_code = error_type
                workflow_run.error_message = error_message
                workflow_run.completed_at = now
            failed_event = OutboxEvent(
                id=event_id,
                aggregate_type="RFP",
                aggregate_id=event.rfp_id,
                topic=self.settings.kafka_rfp_failed_topic,
                event_key=event.rfp_id,
                payload={
                    "event_id": event_id,
                    "event_type": "rfp.failed",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": event.rfp_id,
                    "workflow_run_id": event.workflow_run_id,
                    "stage": "proposal_agent",
                    "error_code": error_type,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(failed_event)
            await session.flush()
        await self.outbox_publisher.publish_event(session, failed_event)
