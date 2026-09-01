from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ProposalNotFoundError, ProposalReviewConflictError
from app.infrastructure.messaging.outbox import OutboxPublisher
from app.infrastructure.storage.minio import ObjectStorageService
from app.models import OutboxEvent, Proposal, ProposalReview
from app.models.enums import (
    OutboxStatus,
    ProposalStatus,
    ReviewDecision,
    RFPStatus,
    WorkflowStatus,
)
from app.models.mixins import generate_uuid, utc_now
from app.repositories import (
    CapabilityResultRepository,
    OutboxEventRepository,
    ProposalRepository,
    ProposalReviewRepository,
    RFPRepository,
    WorkflowRunRepository,
)
from app.schemas.proposal import ProposalReviewCreate


@dataclass(frozen=True, slots=True)
class ProposalReviewOutcome:
    proposal: Proposal
    review: ProposalReview


class ProposalReviewService:
    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        storage: ObjectStorageService,
        outbox_publisher: OutboxPublisher,
    ) -> None:
        self.settings = settings
        self.session = session
        self.storage = storage
        self.outbox_publisher = outbox_publisher

    async def review(
        self,
        proposal_id: str,
        data: ProposalReviewCreate,
    ) -> ProposalReviewOutcome:
        if data.decision == ReviewDecision.APPROVED:
            return await self._approve(proposal_id, data)
        return await self._request_revision(proposal_id, data)

    async def list_reviews(self, proposal_id: str) -> list[ProposalReview]:
        async with self.session.begin():
            proposal = await ProposalRepository(self.session).get(proposal_id)
            if proposal is None:
                raise ProposalNotFoundError(f"proposal {proposal_id} was not found")
            return await ProposalReviewRepository(self.session).list_for_proposal(proposal_id)

    async def _approve(
        self,
        proposal_id: str,
        data: ProposalReviewCreate,
    ) -> ProposalReviewOutcome:
        async with self.session.begin():
            proposal = await ProposalRepository(self.session).get(proposal_id)
            if proposal is None:
                raise ProposalNotFoundError(f"proposal {proposal_id} was not found")
            self._ensure_review_pending(proposal)
            if not proposal.markdown_object_key:
                raise ProposalReviewConflictError("proposal has no Markdown artifact")
            markdown_object_key = proposal.markdown_object_key

        await self.storage.download(self.settings.minio_bucket, markdown_object_key)

        now = utc_now()
        event_id = generate_uuid()
        async with self.session.begin():
            proposal = await ProposalRepository(self.session).get_for_update(proposal_id)
            if proposal is None:
                raise ProposalNotFoundError(f"proposal {proposal_id} was not found")
            self._ensure_review_pending(proposal)
            rfp = await RFPRepository(self.session).get_active_for_update(proposal.rfp_id)
            workflow_run = await WorkflowRunRepository(self.session).get(proposal.workflow_run_id)
            if rfp is None or workflow_run is None:
                raise ProposalReviewConflictError("proposal workflow state was not found")

            review = ProposalReview(
                id=generate_uuid(),
                proposal_id=proposal.id,
                decision=ReviewDecision.APPROVED.value,
                comment=data.comment.strip() if data.comment else None,
            )
            ProposalReviewRepository(self.session).add(review)
            proposal.status = ProposalStatus.APPROVED.value
            proposal.approved_at = now
            rfp.status = RFPStatus.APPROVED.value
            rfp.current_stage = "approved"
            rfp.stage_started_at = now
            rfp.completed_at = now
            rfp.error_message = None
            workflow_run.status = WorkflowStatus.SUCCEEDED.value
            workflow_run.current_node = "end"
            workflow_run.completed_at = now
            workflow_run.output_summary = {
                **workflow_run.output_summary,
                "proposal_approved": True,
                "approved_proposal_id": proposal.id,
                "approved_markdown_object_key": proposal.markdown_object_key,
            }
            event = OutboxEvent(
                id=event_id,
                aggregate_type="Proposal",
                aggregate_id=proposal.id,
                topic=self.settings.kafka_proposal_approved_topic,
                event_key=rfp.id,
                payload={
                    "event_id": event_id,
                    "event_type": "proposal.approved",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": rfp.id,
                    "workflow_run_id": workflow_run.id,
                    "proposal_id": proposal.id,
                    "version": proposal.version,
                    "markdown_object_key": proposal.markdown_object_key,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(self.session).add(event)
            await self.session.flush()

        await self.outbox_publisher.publish_event(self.session, event)
        return ProposalReviewOutcome(proposal, review)

    async def _request_revision(
        self,
        proposal_id: str,
        data: ProposalReviewCreate,
    ) -> ProposalReviewOutcome:
        event_id = generate_uuid()
        async with self.session.begin():
            proposal = await ProposalRepository(self.session).get_for_update(proposal_id)
            if proposal is None:
                raise ProposalNotFoundError(f"proposal {proposal_id} was not found")
            self._ensure_review_pending(proposal)
            rfp = await RFPRepository(self.session).get_active_for_update(proposal.rfp_id)
            workflow_run = await WorkflowRunRepository(self.session).get(proposal.workflow_run_id)
            if rfp is None or workflow_run is None:
                raise ProposalReviewConflictError("proposal workflow state was not found")
            capabilities = await CapabilityResultRepository(self.session).list_for_rfp(rfp.id)

            review = ProposalReview(
                id=generate_uuid(),
                proposal_id=proposal.id,
                decision=data.decision.value,
                comment=(data.comment or "").strip(),
            )
            ProposalReviewRepository(self.session).add(review)
            proposal.status = (
                ProposalStatus.REJECTED.value
                if data.decision == ReviewDecision.REJECTED
                else ProposalStatus.CHANGES_REQUESTED.value
            )
            rfp.status = RFPStatus.PROCESSING.value
            rfp.current_stage = "proposal_revision"
            rfp.stage_started_at = utc_now()
            rfp.error_message = None
            workflow_run.status = WorkflowStatus.RUNNING.value
            workflow_run.current_node = "proposal_agent"
            workflow_run.completed_at = None
            workflow_run.output_summary = {
                **workflow_run.output_summary,
                "proposal_generated": False,
                "proposal_review_decision": data.decision.value,
                "proposal_review_comment": review.comment,
            }
            event = OutboxEvent(
                id=event_id,
                aggregate_type="RFP",
                aggregate_id=rfp.id,
                topic=self.settings.kafka_capabilities_evaluated_topic,
                event_key=rfp.id,
                payload={
                    "event_id": event_id,
                    "event_type": "rfp.capabilities.evaluated",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "rfp_id": rfp.id,
                    "workflow_run_id": workflow_run.id,
                    "capability_count": len(capabilities),
                    "revision_of_proposal_id": proposal.id,
                    "review_decision": data.decision.value,
                    "review_comment": review.comment,
                },
                status=OutboxStatus.PENDING.value,
            )
            OutboxEventRepository(self.session).add(event)
            await self.session.flush()

        await self.outbox_publisher.publish_event(self.session, event)
        return ProposalReviewOutcome(proposal, review)

    @staticmethod
    def _ensure_review_pending(proposal: Proposal) -> None:
        if proposal.status != ProposalStatus.REVIEW_PENDING.value:
            raise ProposalReviewConflictError(f"proposal {proposal.id} is not awaiting review")
