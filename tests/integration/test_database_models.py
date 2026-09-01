import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.session import async_session_factory, engine
from app.models import (
    RFP,
    CapabilityEvidence,
    CapabilityResult,
    Customer,
    Document,
    OutboxEvent,
    Proposal,
    ProposalReview,
    Requirement,
    User,
    WorkflowRun,
)
from app.models.enums import (
    CapabilityStatus,
    DocumentType,
    ReviewDecision,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run database integration tests",
    ),
]


@pytest.mark.asyncio
async def test_complete_model_graph_can_be_persisted() -> None:
    suffix = uuid4().hex
    rfp_id = str(uuid4())
    async with async_session_factory() as session:
        transaction = await session.begin()
        try:
            user = User(
                email=f"integration-{suffix}@example.com",
                display_name="Integration Test User",
            )
            customer = Customer(
                name="Integration Test Customer",
                code=f"TEST-{suffix[:12]}",
                extra_data={},
            )
            rfp = RFP(
                id=rfp_id,
                customer=customer,
                created_by=user,
                title="Integration Test RFP",
                reference_number=f"RFP-{suffix[:12]}",
            )
            document = Document(
                rfp=rfp,
                uploaded_by=user,
                document_type=DocumentType.RFP_SOURCE.value,
                bucket="dealflow",
                object_key=f"integration/{suffix}/rfp.pdf",
                original_filename="rfp.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                checksum_sha256=suffix.ljust(64, "0"),
                extra_data={},
            )
            workflow_run = WorkflowRun(
                rfp=rfp,
                correlation_id=f"integration-{suffix}",
                input_data={},
                output_summary={},
            )
            requirement = Requirement(
                rfp=rfp,
                source_document=document,
                requirement_key="REQ001",
                category="security",
                requirement_text="Support SAML 2.0",
                normalized_text="Support SAML 2.0",
                mandatory=True,
                confidence=Decimal("0.9500"),
                raw_output={},
            )
            capability_result = CapabilityResult(
                requirement=requirement,
                workflow_run=workflow_run,
                status=CapabilityStatus.SUPPORTED.value,
                confidence=Decimal("0.9800"),
                reason="Supported by the platform.",
                reviewed_by=user,
                raw_output={},
            )
            evidence = CapabilityEvidence(
                result=capability_result,
                document=document,
                qdrant_point_id=f"point-{suffix}",
                page_number=3,
                snippet="The platform supports SAML 2.0.",
                retrieval_score=Decimal("0.950000"),
                rerank_score=Decimal("0.970000"),
                rank_position=1,
            )
            proposal = Proposal(
                rfp=rfp,
                workflow_run=workflow_run,
                version=1,
                title="Integration Test Proposal",
            )
            review = ProposalReview(
                proposal=proposal,
                decision=ReviewDecision.APPROVED.value,
                comment="Approved in integration test.",
            )
            outbox_event = OutboxEvent(
                aggregate_type="RFP",
                aggregate_id=rfp_id,
                topic="rfp.uploaded",
                event_key=rfp_id,
                payload={"rfp_id": rfp_id},
            )

            session.add_all(
                [
                    user,
                    customer,
                    rfp,
                    document,
                    workflow_run,
                    requirement,
                    capability_result,
                    evidence,
                    proposal,
                    review,
                    outbox_event,
                ]
            )
            await session.flush()

            result = await session.scalar(
                select(func.count()).select_from(RFP).where(RFP.id == rfp.id)
            )
            assert result == 1
        finally:
            await transaction.rollback()
    await engine.dispose()
