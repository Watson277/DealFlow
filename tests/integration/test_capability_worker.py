import asyncio
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pymupdf
import pytest
from fastapi import UploadFile
from httpx import ASGITransport, AsyncClient, Headers
from qdrant_client import AsyncQdrantClient
from sqlalchemy import delete, select

from app.agents.capability_judge import CapabilityRequirement
from app.agents.proposal_generator import ProposalContext
from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.documents.parser import DocumentParser
from app.infrastructure.messaging.kafka import KafkaProducerService
from app.infrastructure.storage.minio import ObjectStorageService
from app.main import app
from app.models import (
    RFP,
    CapabilityEvidence,
    CapabilityResult,
    Customer,
    Document,
    OutboxEvent,
    Proposal,
    Requirement,
    WorkflowRun,
)
from app.models.enums import (
    CapabilityStatus,
    DocumentStatus,
    DocumentType,
    OutboxStatus,
    RFPStatus,
    WorkflowRunType,
    WorkflowStatus,
)
from app.rag.chunking import KnowledgeChunker
from app.rag.vector_store import QdrantKnowledgeStore, RetrievedEvidence
from app.schemas.capability import CapabilityJudgment
from app.schemas.proposal import ProposalDraft, ProposalRequirementResponse
from app.services.knowledge import KnowledgeService
from app.workers.capability_worker import CapabilityWorker
from app.workers.proposal_worker import ProposalWorker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run infrastructure integration tests",
    ),
]


class FakeEmbeddingService:
    @property
    def dimensions(self) -> int:
        return 3

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] if "saml" in text.lower() else [0.0, 1.0, 0.0] for text in texts]


class FakeCapabilityJudge:
    async def judge(
        self,
        requirement: CapabilityRequirement,
        evidence: list[RetrievedEvidence],
    ) -> CapabilityJudgment:
        assert requirement.key == "REQ-0001"
        assert evidence
        assert "SAML" in evidence[0].text
        return CapabilityJudgment(
            status=CapabilityStatus.SUPPORTED,
            confidence=0.97,
            reason="The active security guide explicitly confirms SAML 2.0 support.",
            customization_notes=None,
            selected_evidence_point_ids=[evidence[0].point_id],
        )


class FakeProposalGenerator:
    async def generate(self, context: ProposalContext) -> ProposalDraft:
        assert context.customer["name"] == "Capability Integration Customer"
        assert len(context.capabilities) == 1
        return ProposalDraft(
            title="StellarCloud Response",
            executive_summary="StellarCloud can meet the documented security requirement.",
            requirement_responses=[
                ProposalRequirementResponse(
                    requirement_key="REQ-0001",
                    requirement="This text is normalized from persisted data.",
                    capability_status=CapabilityStatus.NEED_REVIEW,
                    response="SAML 2.0 single sign-on is supported.",
                    evidence_summary="Security Guide version 3.2 confirms support.",
                    risk_or_gap=None,
                )
            ],
            technical_solution="Use the platform SAML integration.",
            security_compliance="Configure SAML according to the security guide.",
            sla="SLA commitments remain subject to contract review.",
            deployment="Configure and validate SAML during implementation.",
            risks_and_gaps="No material capability gap was identified.",
            commercial_notes="Pricing and contract terms require commercial review.",
        )


def _build_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


@pytest.mark.asyncio
async def test_capability_worker_retrieves_qdrant_evidence_and_persists_results() -> None:
    base_settings = get_settings()
    suffix = uuid4().hex
    settings = base_settings.model_copy(
        update={
            "qdrant_collection": f"dealflow_capability_test_{suffix}",
            "qdrant_score_threshold": 0.1,
            "embedding_dimensions": 3,
            "kafka_capability_worker_group": f"dealflow-capability-test-{suffix}",
        }
    )
    storage = ObjectStorageService(settings)
    embeddings = FakeEmbeddingService()
    knowledge_document: Document | None = None
    knowledge_source_key: str | None = None
    knowledge_parsed_key: str | None = None
    knowledge_parsed_ir_key: str | None = None
    customer_id = str(uuid4())
    rfp_id = str(uuid4())
    source_document_id = str(uuid4())
    requirement_id = str(uuid4())
    workflow_run_id = str(uuid4())
    producer = KafkaProducerService(settings)
    proposal_worker: ProposalWorker | None = None
    proposal_worker_task: asyncio.Task[None] | None = None
    proposal_id: str | None = None
    proposal_markdown_key: str | None = None
    vector_store = QdrantKnowledgeStore(settings)
    worker = CapabilityWorker(
        settings,
        embeddings=embeddings,
        judge=FakeCapabilityJudge(),
        vector_store=vector_store,
    )
    worker_task = asyncio.create_task(worker.run())

    try:
        upload = UploadFile(
            file=BytesIO(_build_pdf("StellarCloud supports SAML 2.0 single sign-on.")),
            filename="security-guide.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        async with async_session_factory() as knowledge_session:
            knowledge_service = KnowledgeService(
                session=knowledge_session,
                storage=storage,
                parser=DocumentParser(),
                chunker=KnowledgeChunker(settings),
                embeddings=embeddings,
                vector_store=QdrantKnowledgeStore(settings),
            )
            knowledge_document = await knowledge_service.ingest(
                upload,
                title="Security Guide",
                category="security",
                version="3.2",
            )
            await knowledge_service.close()
        await upload.close()
        knowledge_source_key = knowledge_document.object_key
        knowledge_parsed_key = knowledge_document.parsed_text_object_key
        knowledge_parsed_ir_key = knowledge_document.parsed_ir_object_key
        assert knowledge_document.status == DocumentStatus.READY.value
        assert knowledge_parsed_ir_key is not None

        async with async_session_factory() as session, session.begin():
            session.add(
                Customer(
                    id=customer_id,
                    name="Capability Integration Customer",
                    code=f"CAP-{suffix[:12]}",
                    extra_data={},
                )
            )
            session.add(
                RFP(
                    id=rfp_id,
                    customer_id=customer_id,
                    title="Capability Integration RFP",
                    status=RFPStatus.PROCESSING.value,
                    current_stage="requirements_extracted",
                )
            )
            session.add(
                Document(
                    id=source_document_id,
                    rfp_id=rfp_id,
                    document_type=DocumentType.RFP_SOURCE.value,
                    status=DocumentStatus.READY.value,
                    bucket=settings.minio_bucket,
                    object_key=f"test/{rfp_id}/source.pdf",
                    original_filename="source.pdf",
                    content_type="application/pdf",
                    size_bytes=1,
                    checksum_sha256="0" * 64,
                    extra_data={},
                )
            )
            session.add(
                WorkflowRun(
                    id=workflow_run_id,
                    rfp_id=rfp_id,
                    run_type=WorkflowRunType.FULL.value,
                    status=WorkflowStatus.RUNNING.value,
                    current_node="capability_agent",
                    correlation_id=str(uuid4()),
                    input_data={},
                    output_summary={"requirements_extracted": True},
                )
            )
            session.add(
                Requirement(
                    id=requirement_id,
                    rfp_id=rfp_id,
                    source_document_id=source_document_id,
                    requirement_key="REQ-0001",
                    category="security",
                    requirement_text="The solution must support SAML 2.0.",
                    normalized_text="Support SAML 2.0",
                    mandatory=True,
                    confidence=Decimal("0.9800"),
                    fingerprint="1" * 64,
                    raw_output={},
                )
            )

        await asyncio.wait_for(worker.started.wait(), timeout=15)
        await producer.publish(
            topic=settings.kafka_requirements_extracted_topic,
            event_key=rfp_id,
            payload={
                "event_id": str(uuid4()),
                "event_type": "rfp.requirements.extracted",
                "occurred_at": datetime.now(UTC).isoformat(),
                "rfp_id": rfp_id,
                "document_id": source_document_id,
                "workflow_run_id": workflow_run_id,
                "requirement_count": 1,
            },
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            deadline = asyncio.get_running_loop().time() + 20
            status_body: dict[str, object] = {}
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(f"/rfps/{rfp_id}/status")
                assert response.status_code == 200, response.text
                status_body = response.json()
                if (
                    status_body["current_stage"] == "capabilities_evaluated"
                    or status_body["status"] == RFPStatus.FAILED.value
                ):
                    break
                await asyncio.sleep(0.25)

            assert status_body["status"] == RFPStatus.PROCESSING.value, status_body
            assert status_body["current_stage"] == "capabilities_evaluated"

            response = await client.get(f"/rfps/{rfp_id}/capabilities")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 1
            result = body["items"][0]
            assert result["requirement_key"] == "REQ-0001"
            assert result["status"] == CapabilityStatus.SUPPORTED.value
            assert result["confidence"] == 0.97
            assert len(result["evidence"]) == 1
            assert result["evidence"][0]["document_id"] == knowledge_document.id
            assert "SAML" in result["evidence"][0]["snippet"]

            proposal_settings = settings.model_copy(
                update={"kafka_proposal_worker_group": f"dealflow-proposal-test-{suffix}"}
            )
            proposal_worker = ProposalWorker(
                proposal_settings,
                generator=FakeProposalGenerator(),
            )
            proposal_worker_task = asyncio.create_task(proposal_worker.run())
            await asyncio.wait_for(proposal_worker.started.wait(), timeout=15)

            deadline = asyncio.get_running_loop().time() + 20
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(f"/rfps/{rfp_id}/status")
                assert response.status_code == 200, response.text
                status_body = response.json()
                if (
                    status_body["current_stage"] == "human_review"
                    or status_body["status"] == RFPStatus.FAILED.value
                ):
                    break
                await asyncio.sleep(0.25)

            assert status_body["status"] == RFPStatus.REVIEW_PENDING.value, status_body
            assert status_body["current_stage"] == "human_review"

            response = await client.get(f"/rfps/{rfp_id}/proposals")
            assert response.status_code == 200, response.text
            proposals = response.json()
            assert proposals["total"] == 1
            proposal = proposals["items"][0]
            proposal_id = proposal["id"]
            proposal_markdown_key = proposal["markdown_object_key"]
            assert proposal["version"] == 1
            assert proposal["status"] == "REVIEW_PENDING"
            matrix = proposal["content"]["requirement_responses"]
            assert matrix[0]["requirement"] == "The solution must support SAML 2.0."
            assert matrix[0]["capability_status"] == CapabilityStatus.SUPPORTED.value

            response = await client.get(f"/proposals/{proposal_id}/markdown")
            assert response.status_code == 200, response.text
            assert response.headers["content-type"].startswith("text/markdown")
            assert "# StellarCloud Response" in response.text
            assert "SUPPORTED" in response.text

        async with async_session_factory() as session, session.begin():
            completed_event = await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == rfp_id,
                    OutboxEvent.topic == settings.kafka_capabilities_evaluated_topic,
                )
            )
            assert completed_event is not None
            assert completed_event.status == OutboxStatus.PUBLISHED.value
            proposal_event = await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.event_key == rfp_id,
                    OutboxEvent.topic == settings.kafka_proposal_generated_topic,
                )
            )
            assert proposal_event is not None
            assert proposal_event.status == OutboxStatus.PUBLISHED.value
    finally:
        if proposal_worker is not None:
            proposal_worker.request_stop()
        if proposal_worker_task is not None:
            await asyncio.wait_for(proposal_worker_task, timeout=10)
        worker.request_stop()
        await asyncio.wait_for(worker_task, timeout=10)
        await producer.stop()
        for object_key in (
            knowledge_source_key,
            knowledge_parsed_key,
            knowledge_parsed_ir_key,
            proposal_markdown_key,
        ):
            if object_key:
                await storage.remove(settings.minio_bucket, object_key)
        cleanup_qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        try:
            if await cleanup_qdrant.collection_exists(settings.qdrant_collection):
                await cleanup_qdrant.delete_collection(settings.qdrant_collection)
        finally:
            await cleanup_qdrant.close()

        async with async_session_factory() as cleanup_session, cleanup_session.begin():
            await cleanup_session.execute(
                delete(CapabilityEvidence).where(
                    CapabilityEvidence.capability_result_id.in_(
                        select(CapabilityResult.id).where(
                            CapabilityResult.workflow_run_id == workflow_run_id
                        )
                    )
                )
            )
            await cleanup_session.execute(
                delete(CapabilityResult).where(CapabilityResult.workflow_run_id == workflow_run_id)
            )
            await cleanup_session.execute(
                delete(OutboxEvent).where(OutboxEvent.event_key == rfp_id)
            )
            if proposal_id is not None:
                await cleanup_session.execute(delete(Proposal).where(Proposal.id == proposal_id))
            await cleanup_session.execute(delete(Requirement).where(Requirement.rfp_id == rfp_id))
            await cleanup_session.execute(delete(Document).where(Document.rfp_id == rfp_id))
            await cleanup_session.execute(delete(WorkflowRun).where(WorkflowRun.rfp_id == rfp_id))
            await cleanup_session.execute(delete(RFP).where(RFP.id == rfp_id))
            await cleanup_session.execute(delete(Customer).where(Customer.id == customer_id))
            if knowledge_document is not None:
                await cleanup_session.execute(
                    delete(Document).where(Document.id == knowledge_document.id)
                )
        await engine.dispose()
