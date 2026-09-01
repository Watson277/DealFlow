from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.capability_judge import (
    CapabilityJudge,
    CapabilityRequirement,
)
from app.core.config import Settings
from app.core.exceptions import CapabilityEvaluationError
from app.db.session import async_session_factory
from app.models import (
    RFP,
    CapabilityEvidence,
    CapabilityResult,
    OutboxEvent,
    Requirement,
    WorkflowRun,
)
from app.models.enums import CapabilityStatus, OutboxStatus, RFPStatus, WorkflowStatus
from app.models.mixins import generate_uuid, utc_now
from app.repositories import (
    CapabilityEvidenceRepository,
    CapabilityResultRepository,
    DocumentRepository,
    OutboxEventRepository,
    RequirementRepository,
    RFPRepository,
    WorkflowRunRepository,
)
from app.schemas.capability import CapabilityJudgment
from app.schemas.events import RequirementsExtractedEvent
from app.services.embedding import EmbeddingService
from app.services.lock import DistributedLockService
from app.services.outbox import OutboxPublisher
from app.services.vector_store import QdrantKnowledgeStore, RetrievedEvidence

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EvaluatedCapability:
    requirement: CapabilityRequirement
    judgment: CapabilityJudgment
    evidence: list[RetrievedEvidence]


class CapabilityProcessingService:
    def __init__(
        self,
        *,
        settings: Settings,
        embeddings: EmbeddingService,
        vector_store: QdrantKnowledgeStore,
        judge: CapabilityJudge,
        locks: DistributedLockService,
        outbox_publisher: OutboxPublisher,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.judge = judge
        self.locks = locks
        self.outbox_publisher = outbox_publisher

    async def process(self, event: RequirementsExtractedEvent) -> None:
        async with self.locks.lock(
            f"lock:capabilities:{event.rfp_id}",
            ttl_seconds=self.settings.capability_lock_ttl_seconds,
        ):
            await self._process_locked(event)

    async def _process_locked(self, event: RequirementsExtractedEvent) -> None:
        async with async_session_factory() as session:
            try:
                entities = await self._mark_evaluating(session, event)
            except Exception as exc:
                await self._mark_failed(session, event, exc)
                return
            if entities is None:
                return
            rfp, workflow_run, requirements = entities

            try:
                capability_requirements = [
                    CapabilityRequirement(
                        id=item.id,
                        key=item.requirement_key,
                        text=item.normalized_text,
                        category=item.category,
                        mandatory=item.mandatory,
                        rfp_id=rfp.id,
                    )
                    for item in requirements
                ]
                query_texts = [
                    f"Category: {item.category}\nRequirement: {item.text}"
                    for item in capability_requirements
                ]
                vectors = await self.embeddings.embed(query_texts)
                if len(vectors) != len(capability_requirements):
                    raise CapabilityEvaluationError(
                        "requirement count does not match embedding count"
                    )

                evaluated: list[EvaluatedCapability] = []
                for requirement, vector in zip(
                    capability_requirements,
                    vectors,
                    strict=True,
                ):
                    async with session.begin():
                        if await RFPRepository(session).get_active(event.rfp_id) is None:
                            return
                    evidence = await self.vector_store.search(vector)
                    async with session.begin():
                        active_ids = await DocumentRepository(session).active_knowledge_ids(
                            [item.document_id for item in evidence]
                        )
                    evidence = [item for item in evidence if item.document_id in active_ids]
                    judgment = (
                        await self.judge.judge(requirement, evidence)
                        if evidence
                        else self._no_evidence_judgment()
                    )
                    evaluated.append(
                        EvaluatedCapability(
                            requirement=requirement,
                            judgment=judgment,
                            evidence=evidence,
                        )
                    )
                completion_event = await self._save_results(session, event, evaluated)
            except Exception as exc:
                await self._mark_failed(session, event, exc)
                logger.warning(
                    "capability_evaluation_failed",
                    rfp_id=event.rfp_id,
                    error_type=type(exc).__name__,
                )
                return

            await self.outbox_publisher.publish_event(session, completion_event)
            logger.info(
                "capabilities_evaluated",
                rfp_id=rfp.id,
                workflow_run_id=workflow_run.id,
                capability_count=len(evaluated),
            )

    async def _mark_evaluating(
        self,
        session: AsyncSession,
        event: RequirementsExtractedEvent,
    ) -> tuple[RFP, WorkflowRun, list[Requirement]] | None:
        now = utc_now()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is None:
                logger.info("capability_event_ignored_missing_rfp", rfp_id=event.rfp_id)
                return None
            if workflow_run is None or workflow_run.rfp_id != rfp.id:
                raise CapabilityEvaluationError("workflow run was not found for RFP")
            if workflow_run.output_summary.get("capabilities_evaluated") is True:
                logger.info("capability_event_already_processed", rfp_id=rfp.id)
                return None
            requirements = await RequirementRepository(session).list_for_rfp(rfp.id)
            if len(requirements) != event.requirement_count:
                raise CapabilityEvaluationError(
                    "persisted requirement count does not match extraction event"
                )

            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "evaluate_capabilities"
            rfp.stage_started_at = now
            rfp.error_message = None
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "capability_agent"
            workflow_run.error_code = None
            workflow_run.error_message = None
        return rfp, workflow_run, list(requirements)

    async def _save_results(
        self,
        session: AsyncSession,
        event: RequirementsExtractedEvent,
        evaluated: list[EvaluatedCapability],
    ) -> OutboxEvent:
        completion_event_id = generate_uuid()
        now = utc_now()
        async with session.begin():
            rfp = await RFPRepository(session).get_active_for_update(event.rfp_id)
            workflow_run = await WorkflowRunRepository(session).get(event.workflow_run_id)
            if rfp is None or workflow_run is None:
                raise CapabilityEvaluationError("RFP capability state disappeared")

            result_repository = CapabilityResultRepository(session)
            evidence_repository = CapabilityEvidenceRepository(session)
            for evaluated_item in evaluated:
                result_id = generate_uuid()
                judgment = evaluated_item.judgment
                result_repository.add(
                    CapabilityResult(
                        id=result_id,
                        requirement_id=evaluated_item.requirement.id,
                        workflow_run_id=workflow_run.id,
                        status=judgment.status.value,
                        confidence=Decimal(str(round(judgment.confidence, 4))),
                        reason=judgment.reason.strip(),
                        customization_notes=(
                            judgment.customization_notes.strip()
                            if judgment.customization_notes
                            else None
                        ),
                        model_name=self.settings.llm_model,
                        prompt_version=self.settings.capability_prompt_version,
                        raw_output=judgment.model_dump(mode="json"),
                    )
                )
                for rank, evidence in enumerate(evaluated_item.evidence, start=1):
                    evidence_repository.add(
                        CapabilityEvidence(
                            id=generate_uuid(),
                            capability_result_id=result_id,
                            document_id=evidence.document_id,
                            qdrant_point_id=evidence.point_id,
                            page_number=evidence.page_number,
                            snippet=evidence.text,
                            retrieval_score=Decimal(str(round(evidence.score, 6))),
                            rerank_score=None,
                            rank_position=rank,
                        )
                    )

            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "capabilities_evaluated"
            rfp.stage_started_at = now
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "proposal_agent"
            workflow_run.output_summary = {
                **workflow_run.output_summary,
                "capability_count": len(evaluated),
                "capabilities_evaluated": True,
            }
            completion_event = OutboxEvent(
                id=completion_event_id,
                aggregate_type="RFP",
                aggregate_id=rfp.id,
                topic=self.settings.kafka_capabilities_evaluated_topic,
                event_key=rfp.id,
                payload={
                    "event_id": completion_event_id,
                    "event_type": "rfp.capabilities.evaluated",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": rfp.id,
                    "workflow_run_id": workflow_run.id,
                    "capability_count": len(evaluated),
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(completion_event)
            await session.flush()
        return completion_event

    async def _mark_failed(
        self,
        session: AsyncSession,
        event: RequirementsExtractedEvent,
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
                rfp.current_stage = "evaluate_capabilities"
                rfp.error_message = error_message
            if workflow_run is not None:
                workflow_run.status = WorkflowStatus.FAILED.value
                workflow_run.current_node = "capability_agent"
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
                    "workflow_run_id": event.workflow_run_id,
                    "stage": "capability_agent",
                    "error_code": error_type,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(session).add(failed_event)
            await session.flush()
        await self.outbox_publisher.publish_event(session, failed_event)

    @staticmethod
    def _no_evidence_judgment() -> CapabilityJudgment:
        return CapabilityJudgment(
            status=CapabilityStatus.NEED_REVIEW,
            confidence=0,
            reason="No active enterprise knowledge evidence was retrieved.",
            customization_notes=None,
            selected_evidence_point_ids=[],
        )
