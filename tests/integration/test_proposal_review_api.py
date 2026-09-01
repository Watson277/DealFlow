import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.infrastructure.messaging.kafka import get_kafka_service
from app.infrastructure.storage.minio import ObjectStorageService
from app.main import app
from app.models import RFP, Customer, OutboxEvent, Proposal, ProposalReview, WorkflowRun
from app.models.enums import (
    OutboxStatus,
    ProposalStatus,
    RFPStatus,
    WorkflowRunType,
    WorkflowStatus,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run infrastructure integration tests",
    ),
]


@pytest.mark.asyncio
async def test_review_revision_and_approve_markdown_proposals() -> None:
    settings = get_settings()
    storage = ObjectStorageService(settings)
    suffix = uuid4().hex
    customer_id = str(uuid4())
    rfp_id = str(uuid4())
    workflow_run_id = str(uuid4())
    first_proposal_id = str(uuid4())
    second_proposal_id = str(uuid4())
    first_key = f"proposal/{rfp_id}/v1/{first_proposal_id}.md"
    second_key = f"proposal/{rfp_id}/v2/{second_proposal_id}.md"

    await storage.upload_text(first_key, "# First proposal\n", content_type="text/markdown")
    try:
        async with async_session_factory() as session, session.begin():
            session.add(
                Customer(
                    id=customer_id,
                    name="Review API Customer",
                    code=f"REV-{suffix[:12]}",
                    extra_data={},
                )
            )
            session.add(
                RFP(
                    id=rfp_id,
                    customer_id=customer_id,
                    title="Review API RFP",
                    status=RFPStatus.REVIEW_PENDING.value,
                    current_stage="human_review",
                )
            )
            session.add(
                WorkflowRun(
                    id=workflow_run_id,
                    rfp_id=rfp_id,
                    run_type=WorkflowRunType.FULL.value,
                    status=WorkflowStatus.WAITING_REVIEW.value,
                    current_node="human_review",
                    correlation_id=str(uuid4()),
                    input_data={},
                    output_summary={"proposal_generated": True},
                )
            )
            session.add(
                Proposal(
                    id=first_proposal_id,
                    rfp_id=rfp_id,
                    workflow_run_id=workflow_run_id,
                    version=1,
                    status=ProposalStatus.REVIEW_PENDING.value,
                    title="First proposal",
                    executive_summary="Initial version",
                    markdown_object_key=first_key,
                    content={},
                )
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            invalid = await client.post(
                f"/proposals/{first_proposal_id}/reviews",
                json={
                    "decision": "CHANGES_REQUESTED",
                },
            )
            assert invalid.status_code == 422

            revision = await client.post(
                f"/proposals/{first_proposal_id}/reviews",
                json={
                    "decision": "CHANGES_REQUESTED",
                    "comment": "Add a clearer rollout plan.",
                },
            )
            assert revision.status_code == 200, revision.text
            revision_body = revision.json()
            assert revision_body["proposal"]["status"] == "CHANGES_REQUESTED"
            assert "reviewer_id" not in revision_body["review"]

            history = await client.get(f"/proposals/{first_proposal_id}/reviews")
            assert history.status_code == 200, history.text
            assert history.json()["total"] == 1
            assert history.json()["items"][0]["comment"] == "Add a clearer rollout plan."

        async with async_session_factory() as session, session.begin():
            rfp = await session.get(RFP, rfp_id)
            workflow = await session.get(WorkflowRun, workflow_run_id)
            assert rfp is not None
            assert workflow is not None
            assert rfp.status == RFPStatus.PROCESSING.value
            assert rfp.current_stage == "proposal_revision"
            assert workflow.status == WorkflowStatus.RUNNING.value
            assert workflow.output_summary["proposal_generated"] is False
            assert workflow.output_summary["proposal_review_comment"] == (
                "Add a clearer rollout plan."
            )

            revision_event = await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == rfp_id,
                    OutboxEvent.topic == settings.kafka_capabilities_evaluated_topic,
                )
            )
            assert revision_event is not None
            assert revision_event.status == OutboxStatus.PUBLISHED.value

            rfp.status = RFPStatus.REVIEW_PENDING.value
            rfp.current_stage = "human_review"
            workflow.status = WorkflowStatus.WAITING_REVIEW.value
            workflow.current_node = "human_review"
            workflow.output_summary = {
                **workflow.output_summary,
                "proposal_generated": True,
                "proposal_id": second_proposal_id,
                "proposal_version": 2,
            }
            session.add(
                Proposal(
                    id=second_proposal_id,
                    rfp_id=rfp_id,
                    workflow_run_id=workflow_run_id,
                    version=2,
                    status=ProposalStatus.REVIEW_PENDING.value,
                    title="Second proposal",
                    executive_summary="Revised version",
                    markdown_object_key=second_key,
                    content={},
                )
            )

        await storage.upload_text(second_key, "# Second proposal\n", content_type="text/markdown")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            approved = await client.post(
                f"/proposals/{second_proposal_id}/reviews",
                json={
                    "decision": "APPROVED",
                    "comment": "Approved for delivery.",
                },
            )
            assert approved.status_code == 200, approved.text
            approved_body = approved.json()
            assert approved_body["proposal"]["status"] == "APPROVED"
            assert "approved_by_id" not in approved_body["proposal"]
            assert approved_body["proposal"]["approved_at"] is not None

            markdown = await client.get(f"/proposals/{second_proposal_id}/markdown")
            assert markdown.status_code == 200, markdown.text
            assert markdown.text == "# Second proposal\n"

            duplicate = await client.post(
                f"/proposals/{second_proposal_id}/reviews",
                json={"decision": "APPROVED"},
            )
            assert duplicate.status_code == 409

        async with async_session_factory() as session, session.begin():
            rfp = await session.get(RFP, rfp_id)
            workflow = await session.get(WorkflowRun, workflow_run_id)
            assert rfp is not None
            assert workflow is not None
            assert rfp.status == RFPStatus.APPROVED.value
            assert rfp.current_stage == "approved"
            assert rfp.completed_at is not None
            assert workflow.status == WorkflowStatus.SUCCEEDED.value
            assert workflow.current_node == "end"
            assert workflow.completed_at is not None

            approved_event = await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == second_proposal_id,
                    OutboxEvent.topic == settings.kafka_proposal_approved_topic,
                )
            )
            assert approved_event is not None
            assert approved_event.status == OutboxStatus.PUBLISHED.value
    finally:
        await get_kafka_service().stop()
        for object_key in (first_key, second_key):
            await storage.remove(settings.minio_bucket, object_key)
        async with async_session_factory() as session, session.begin():
            await session.execute(
                delete(ProposalReview).where(
                    ProposalReview.proposal_id.in_([first_proposal_id, second_proposal_id])
                )
            )
            await session.execute(delete(OutboxEvent).where(OutboxEvent.event_key == rfp_id))
            await session.execute(delete(Proposal).where(Proposal.rfp_id == rfp_id))
            await session.execute(delete(WorkflowRun).where(WorkflowRun.rfp_id == rfp_id))
            await session.execute(delete(RFP).where(RFP.id == rfp_id))
            await session.execute(delete(Customer).where(Customer.id == customer_id))
        await engine.dispose()
