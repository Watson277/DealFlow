import asyncio
import json
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, MockTransport, Response
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agents.requirement_extractor import OpenAIRequirementExtractor
from app.api.dependencies import get_knowledge_service, get_rfp_service
from app.core.config import get_settings
from app.core.exceptions import CustomerNotFoundError, DealFlowError, RFPRetryConflictError
from app.db.session import get_db_session
from app.infrastructure.storage.minio import StoredObject
from app.main import create_app
from app.models import RFP, Customer, Document, OutboxEvent, Proposal, Requirement, WorkflowRun
from app.models.mixins import utc_now
from app.schemas.events import (
    CapabilitiesEvaluatedEvent,
    RequirementsExtractedEvent,
    RFPCompletedEvent,
    RFPUploadedEvent,
)
from app.schemas.requirement import ExtractedRequirement
from app.services.customer import CustomerService
from app.services.knowledge import KnowledgeService
from app.services.rfp import CreateRFPCommand, RFPService
from app.services.structured_chat import StructuredChatClient
from app.workflow.stages.evaluate_capabilities import CapabilityProcessingService
from app.workflow.stages.extract_requirements import RequirementProcessingService
from app.workflow.stages.generate_proposal import ProposalProcessingService
from app.workflow.stages.parse_rfp import RFPProcessingService


def deletion_app(state, vector_store=None):
    app = create_app()

    async def provide_session():
        async with state.factory() as session:
            yield session

    async def provide_rfp():
        async with state.factory() as session:
            yield service(state, session)

    async def provide_knowledge():
        async with state.factory() as session:
            yield KnowledgeService(
                session=session,
                storage=Mock(),
                parser=Mock(),
                chunker=Mock(),
                embeddings=Mock(),
                vector_store=vector_store,
            )

    app.dependency_overrides[get_db_session] = provide_session
    app.dependency_overrides[get_rfp_service] = provide_rfp
    app.dependency_overrides[get_knowledge_service] = provide_knowledge
    return app


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="requires local MySQL",
    ),
]


@pytest_asyncio.fixture
async def retry_state():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    rfp_id, customer_id, document_id, workflow_id = [str(uuid4()) for _ in range(4)]
    publisher = SimpleNamespace(publish_event=AsyncMock(return_value="PENDING"))
    now = utc_now()
    try:
        async with factory() as session, session.begin():
            session.add(Customer(id=customer_id, name="Retry verification", code=customer_id))
            await session.flush()
            session.add(
                RFP(
                    id=rfp_id,
                    customer_id=customer_id,
                    title="Retry verification",
                    status="FAILED",
                    current_stage="extract_requirements",
                    error_message="request timeout",
                    stage_started_at=now,
                    processing_started_at=now - timedelta(seconds=60),
                )
            )
            await session.flush()
            session.add(
                Document(
                    id=document_id,
                    rfp_id=rfp_id,
                    document_type="RFP_SOURCE",
                    status="READY",
                    bucket="retry-test",
                    object_key=rfp_id,
                    original_filename="rfp.pdf",
                    content_type="application/pdf",
                    size_bytes=1,
                    checksum_sha256="0" * 64,
                    parsed_text_object_key=f"{rfp_id}/parsed.txt",
                )
            )
            session.add(
                WorkflowRun(
                    id=workflow_id,
                    rfp_id=rfp_id,
                    status="FAILED",
                    correlation_id=str(uuid4()),
                    error_code="TimeoutError",
                    error_message="request timeout",
                    completed_at=now,
                    started_at=now - timedelta(seconds=60),
                    output_summary={},
                )
            )
        yield SimpleNamespace(
            settings=settings,
            factory=factory,
            rfp_id=rfp_id,
            document_id=document_id,
            workflow_id=workflow_id,
            publisher=publisher,
        )
    finally:
        # Only these fixture-owned rows are removed; no Kafka or LLM call is made.
        async with factory() as session, session.begin():
            await session.execute(delete(Proposal).where(Proposal.rfp_id == rfp_id))
            await session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id == rfp_id))
            await session.execute(delete(Requirement).where(Requirement.rfp_id == rfp_id))
            await session.execute(delete(Document).where(Document.id == document_id))
            await session.execute(delete(WorkflowRun).where(WorkflowRun.id == workflow_id))
            await session.execute(delete(RFP).where(RFP.id == rfp_id))
            await session.execute(delete(Customer).where(Customer.id == customer_id))
        await engine.dispose()


def service(state, session):
    return RFPService(
        settings=state.settings, session=session, storage=Mock(), outbox_publisher=state.publisher
    )


@pytest.mark.parametrize(
    "stage,event_type,event_model",
    [
        ("parse_document", "rfp.uploaded", RFPUploadedEvent),
        ("extract_requirements", "rfp.completed", RFPCompletedEvent),
        ("evaluate_capabilities", "rfp.requirements.extracted", RequirementsExtractedEvent),
        ("generate_proposal", "rfp.capabilities.evaluated", CapabilitiesEvaluatedEvent),
    ],
)
async def test_retry_routes_to_failed_stage_and_commits_outbox(
    retry_state, stage, event_type, event_model
):
    state = retry_state
    async with state.factory() as session, session.begin():
        rfp = await session.get(RFP, state.rfp_id)
        rfp.current_stage = stage
        document = await session.get(Document, state.document_id)
        document.status = "FAILED" if stage == "parse_document" else "READY"

    app = create_app()

    async def provide_service():
        async with state.factory() as session:
            yield service(state, session)

    app.dependency_overrides[get_rfp_service] = provide_service
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.post(f"/rfps/{state.rfp_id}/retry")
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["attempt"] == 1
        assert body["event_status"] == "PENDING"
        assert body["retried_stage"] == stage
        assert (await client.post(f"/rfps/{state.rfp_id}/retry")).status_code == 409
        status = (await client.get(f"/rfps/{state.rfp_id}/status")).json()
        assert status["status"] == "QUEUED"
        assert status["error_message"] is None
        assert status["stage_started_at"] is not None
        assert status["attempt"] == 1
        assert (await client.post(f"/rfps/{uuid4()}/retry")).status_code == 404

    async with state.factory() as session, session.begin():
        events = (
            await session.scalars(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == state.rfp_id)
            )
        ).all()
        assert len(events) == 1
        assert events[0].topic == event_type
        event_model.model_validate(events[0].payload)
        workflow = await session.get(WorkflowRun, state.workflow_id)
        assert workflow.error_code is None
        assert workflow.completed_at is None
        assert workflow.started_at is not None


async def test_concurrent_retry_only_enqueues_once(retry_state):
    state = retry_state

    async def retry():
        async with state.factory() as session:
            try:
                await service(state, session).retry(state.rfp_id)
                return 202
            except RFPRetryConflictError:
                return 409

    assert sorted(await asyncio.gather(retry(), retry())) == [202, 409]
    state.publisher.publish_event.assert_awaited_once()


@pytest.mark.parametrize("invalid", ["missing_text", "already_completed", "not_failed"])
async def test_retry_invalid_state_rolls_back(retry_state, invalid):
    state = retry_state
    async with state.factory() as session, session.begin():
        if invalid == "missing_text":
            document = await session.get(Document, state.document_id)
            document.parsed_text_object_key = None
        elif invalid == "already_completed":
            workflow = await session.get(WorkflowRun, state.workflow_id)
            workflow.output_summary = {"requirements_extracted": True}
        else:
            rfp = await session.get(RFP, state.rfp_id)
            rfp.status = "APPROVED"
    async with state.factory() as session:
        with pytest.raises(RFPRetryConflictError):
            await service(state, session).retry(state.rfp_id)
    async with state.factory() as session, session.begin():
        assert (
            await session.scalar(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == state.rfp_id)
            )
            is None
        )
        workflow = await session.get(WorkflowRun, state.workflow_id)
        assert workflow.attempt == 0


async def test_requirement_retry_resumes_and_duplicate_delivery_is_idempotent(
    retry_state, monkeypatch
):
    state = retry_state
    async with state.factory() as session:
        result = await service(state, session).retry(state.rfp_id)
    event = RFPCompletedEvent.model_validate(result.event.payload)
    monkeypatch.setattr(
        "app.workflow.stages.extract_requirements.async_session_factory", state.factory
    )
    extractor = SimpleNamespace(
        extract=AsyncMock(
            return_value=[
                ExtractedRequirement(
                    category="security",
                    requirement_text="Support SAML",
                    normalized_text="Support SAML",
                    mandatory=True,
                    confidence=0.95,
                )
            ]
        )
    )
    processor = RequirementProcessingService(
        settings=state.settings,
        storage=SimpleNamespace(download=AsyncMock(return_value=b"SAML")),
        extractor=extractor,
        locks=Mock(),
        outbox_publisher=state.publisher,
    )
    await processor._process_locked(event)
    await processor._process_locked(event)
    extractor.extract.assert_awaited_once()
    async with state.factory() as session, session.begin():
        rfp = await session.get(RFP, state.rfp_id)
        assert rfp.current_stage == "requirements_extracted"
        assert rfp.status == "PROCESSING"
        requirements = (
            await session.scalars(select(Requirement).where(Requirement.rfp_id == state.rfp_id))
        ).all()
    assert len(requirements) == 1


@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_schema_repair_only_persists_validated_requirements(
    retry_state, monkeypatch, repair_succeeds
):
    state = retry_state
    async with state.factory() as session:
        result = await service(state, session).retry(state.rfp_id)
    event = RFPCompletedEvent.model_validate(result.event.payload)
    monkeypatch.setattr(
        "app.workflow.stages.extract_requirements.async_session_factory", state.factory
    )
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        # The same two field violations as the regression unit tests; never use
        # the real provider or publish Kafka events from this test.
        valid = calls == 2 and repair_succeeds
        payload = {
            "requirements": [
                {
                    "category": "security",
                    "requirement_text": "SAML is required.",
                    "normalized_text": "Support SAML.",
                    "mandatory": True,
                    "confidence": 0.9 if valid else 95,
                    "source_page_start": None if valid else 0,
                }
            ]
        }
        return Response(
            200,
            json={
                "id": "chatcmpl-integration",
                "object": "chat.completion",
                "created": 0,
                "model": "glm-5.3-flash",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(payload)},
                    }
                ],
            },
        )

    async with AsyncClient(transport=MockTransport(handle)) as http_client:
        mocked_chat = StructuredChatClient(
            state.settings, AsyncOpenAI(api_key="test", http_client=http_client)
        )
        monkeypatch.setattr(
            "app.agents.requirement_extractor.StructuredChatClient", lambda settings: mocked_chat
        )
        processor = RequirementProcessingService(
            settings=state.settings,
            storage=SimpleNamespace(download=AsyncMock(return_value=b"SAML is required.")),
            extractor=OpenAIRequirementExtractor(state.settings),
            locks=Mock(),
            outbox_publisher=state.publisher,
        )
        await processor._process_locked(event)
    assert calls == 2
    async with state.factory() as session, session.begin():
        rfp = await session.get(RFP, state.rfp_id)
        workflow = await session.get(WorkflowRun, state.workflow_id)
        requirements = (
            await session.scalars(select(Requirement).where(Requirement.rfp_id == state.rfp_id))
        ).all()
        topics = (
            await session.scalars(
                select(OutboxEvent.topic).where(OutboxEvent.aggregate_id == state.rfp_id)
            )
        ).all()
        if repair_succeeds:
            assert len(requirements) == 1
            assert float(requirements[0].confidence) == 0.9
            assert requirements[0].source_page_start is None
            assert rfp.current_stage == "requirements_extracted"
            assert rfp.status == "PROCESSING"
            assert workflow.output_summary["requirements_extracted"] is True
            assert topics.count("rfp.requirements.extracted") == 1
            assert "rfp.failed" not in topics
        else:
            assert requirements == []
            assert rfp.status == "FAILED"
            assert workflow.status == "FAILED"
            assert rfp.current_stage == "extract_requirements"
            assert "schema (2 errors)" in rfp.error_message
            assert not workflow.output_summary.get("requirements_extracted")
            assert "rfp.requirements.extracted" not in topics
            assert topics.count("rfp.failed") == 1


@pytest.mark.parametrize(
    "rfp_status", ["QUEUED", "PROCESSING", "REVIEW_PENDING", "APPROVED", "FAILED"]
)
async def test_delete_rfp_hides_children_and_cancels_pending_work(retry_state, rfp_status):
    state = retry_state
    async with state.factory() as session:
        await service(state, session).retry(state.rfp_id)
    proposal_id = str(uuid4())
    async with state.factory() as session, session.begin():
        rfp = await session.get(RFP, state.rfp_id)
        rfp.status = rfp_status
        session.add(
            Proposal(
                id=proposal_id,
                rfp_id=state.rfp_id,
                workflow_run_id=state.workflow_id,
                version=1,
                title="Delete test proposal",
                status="REVIEW_PENDING",
                markdown_object_key="test-preserved.md",
                content={},
            )
        )
    app = deletion_app(state)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.delete(f"/rfps/{state.rfp_id}")
        assert response.status_code == 204, response.text
        assert response.content == b""
        for suffix in ["", "/status", "/requirements", "/capabilities", "/proposals"]:
            assert (await client.get(f"/rfps/{state.rfp_id}{suffix}")).status_code == 404
        for suffix in ["", "/markdown", "/reviews"]:
            assert (await client.get(f"/proposals/{proposal_id}{suffix}")).status_code == 404
        for decision in ["APPROVED", "CHANGES_REQUESTED"]:
            response = await client.post(
                f"/proposals/{proposal_id}/reviews",
                json={
                    "decision": decision,
                    "comment": "No access after deletion",
                },
            )
            assert response.status_code == 404, response.text
        assert (await client.post(f"/rfps/{state.rfp_id}/retry")).status_code == 404
        assert (await client.delete(f"/rfps/{state.rfp_id}")).status_code == 404
        page = (await client.get("/rfps", params={"search": "Retry verification"})).json()
        assert state.rfp_id not in [item["id"] for item in page["items"]]
    async with state.factory() as session, session.begin():
        rfp = await session.get(RFP, state.rfp_id)
        assert rfp.deleted_at is not None
        assert rfp.status == "ARCHIVED"
        assert (await session.get(WorkflowRun, state.workflow_id)).status == "CANCELLED"
        assert (await session.get(Document, state.document_id)).object_key == state.rfp_id
        event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == state.rfp_id)
        )
        assert event.status == "FAILED"
        assert event.last_error == "RFP_DELETED"


async def test_customer_deletion_rejects_linked_tasks_then_hides_customer(retry_state):
    state = retry_state
    async with state.factory() as session:
        customer_id = (await session.get(RFP, state.rfp_id)).customer_id
    async with AsyncClient(
        transport=ASGITransport(deletion_app(state)), base_url="http://test"
    ) as client:
        response = await client.delete(f"/customers/{customer_id}")
        assert response.status_code == 409
        assert "关联任务" in response.json()["detail"]
        assert (await client.get(f"/customers/{customer_id}")).status_code == 200
        assert (await client.delete(f"/rfps/{state.rfp_id}")).status_code == 204
        assert (await client.delete(f"/customers/{customer_id}")).status_code == 204
        assert (await client.get(f"/customers/{customer_id}")).status_code == 404
        page = (await client.get("/customers", params={"search": customer_id})).json()
        assert page["total"] == 0
        assert (await client.delete(f"/customers/{customer_id}")).status_code == 404
        # A deleted customer's code is reserved, and uploads must not resurrect it.
        response = await client.post("/customers", json={"name": "Duplicate", "code": customer_id})
        assert response.status_code == 409
        response = await client.post(
            "/rfps",
            data={"customer_id": customer_id, "title": "Hidden"},
            files={"file": ("test.pdf", b"%PDF-test", "application/pdf")},
        )
        assert response.status_code == 404


@pytest.mark.parametrize(
    "index_status,vector_failure,expected",
    [
        ("READY", False, 204),
        ("FAILED", False, 204),
        ("INDEXING", False, 409),
        ("READY", True, 503),
    ],
)
async def test_knowledge_deletion_is_scoped_and_preserves_files(
    retry_state, index_status, vector_failure, expected
):
    state = retry_state
    async with state.factory() as session, session.begin():
        document = await session.get(Document, state.document_id)
        document.rfp_id = None
        document.document_type = "KNOWLEDGE"
        document.status = index_status
        document.extra_data = {
            "knowledge_status": "ACTIVE",
            "qdrant_collection": "original-collection",
        }
    vector_store = SimpleNamespace(
        delete_document=AsyncMock(side_effect=RuntimeError("private") if vector_failure else None),
        close=AsyncMock(),
    )
    async with AsyncClient(
        transport=ASGITransport(deletion_app(state, vector_store)), base_url="http://test"
    ) as client:
        response = await client.delete(f"/knowledge/{state.document_id}")
        assert response.status_code == expected, response.text
        if expected == 204:
            assert response.content == b""
            page = (await client.get("/knowledge", params={"limit": 100})).json()
            assert state.document_id not in [item["id"] for item in page["items"]]
            assert (await client.delete(f"/knowledge/{state.document_id}")).status_code == 404
        else:
            assert "private" not in response.text
    if index_status == "INDEXING":
        vector_store.delete_document.assert_not_awaited()
    else:
        vector_store.delete_document.assert_awaited_once_with(
            state.document_id, collection_name="original-collection"
        )
    async with state.factory() as session:
        document = await session.get(Document, state.document_id)
        assert document.status == ("ARCHIVED" if expected == 204 else index_status)
        assert document.object_key == state.rfp_id  # Retained for recovery / historical evidence.
        assert document.extra_data["knowledge_status"] == (
            "DELETED" if expected == 204 else "ACTIVE"
        )


async def test_delete_missing_and_invalid_targets_has_no_side_effects(retry_state):
    state = retry_state
    vectors = SimpleNamespace(delete_document=AsyncMock(), close=AsyncMock())
    async with AsyncClient(
        transport=ASGITransport(deletion_app(state, vectors)), base_url="http://test"
    ) as client:
        for path in ["rfps", "customers", "knowledge"]:
            assert (await client.delete(f"/{path}/{uuid4()}")).status_code == 404
            assert (await client.delete(f"/{path}/not-a-uuid")).status_code == 422
        # Knowledge deletion must never accept an RFP source document ID.
        assert (await client.delete(f"/knowledge/{state.document_id}")).status_code == 404
    vectors.delete_document.assert_not_awaited()


@pytest.mark.parametrize("late_failure", [False, True])
async def test_delete_during_extraction_drops_late_results_and_failures(
    retry_state, monkeypatch, late_failure
):
    state = retry_state
    async with state.factory() as session:
        result = await service(state, session).retry(state.rfp_id)
    event = RFPCompletedEvent.model_validate(result.event.payload)
    monkeypatch.setattr(
        "app.workflow.stages.extract_requirements.async_session_factory", state.factory
    )

    async def extract(*args, **kwargs):
        async with state.factory() as delete_session:
            await service(state, delete_session).delete(state.rfp_id)
        if late_failure:
            raise RuntimeError("late extraction failure")
        return [
            ExtractedRequirement(
                category="security",
                requirement_text="SAML",
                normalized_text="SAML",
                mandatory=True,
                confidence=0.9,
            )
        ]

    extractor = SimpleNamespace(extract=AsyncMock(side_effect=extract))
    processor = RequirementProcessingService(
        settings=state.settings,
        storage=SimpleNamespace(download=AsyncMock(return_value=b"SAML")),
        extractor=extractor,
        locks=Mock(),
        outbox_publisher=state.publisher,
    )
    await processor._process_locked(event)
    await processor._process_locked(event)  # An old Kafka delivery is now ignored.
    extractor.extract.assert_awaited_once()
    async with state.factory() as session:
        rfp = await session.get(RFP, state.rfp_id)
        assert rfp.deleted_at is not None and rfp.status == "ARCHIVED"
        assert (await session.get(WorkflowRun, state.workflow_id)).status == "CANCELLED"
        assert (
            await session.scalars(select(Requirement).where(Requirement.rfp_id == state.rfp_id))
        ).all() == []
        events = (
            await session.scalars(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == state.rfp_id)
            )
        ).all()
        assert len(events) == 1 and events[0].last_error == "RFP_DELETED"


@pytest.mark.parametrize("stage", ["parse", "capability", "proposal"])
async def test_all_workers_ignore_deleted_tasks_at_start_save_and_failure(retry_state, stage):
    state = retry_state
    async with state.factory() as session:
        await service(state, session).delete(state.rfp_id)
    event = SimpleNamespace(
        rfp_id=state.rfp_id, document_id=state.document_id, workflow_run_id=state.workflow_id
    )
    if stage == "parse":
        processor = RFPProcessingService(state.settings, Mock(), Mock(), Mock(), state.publisher)
        start = processor._mark_processing

        def save(session):
            return processor._mark_completed(
                session, event, parsed_object_key="late.txt", page_count=1, text_size=10
            )
    elif stage == "capability":
        processor = CapabilityProcessingService(
            settings=state.settings,
            embeddings=Mock(),
            vector_store=Mock(),
            judge=Mock(),
            locks=Mock(),
            outbox_publisher=state.publisher,
        )
        start = processor._mark_evaluating

        def save(session):
            return processor._save_results(session, event, [])
    else:
        processor = ProposalProcessingService(
            settings=state.settings,
            storage=Mock(),
            generator=Mock(),
            renderer=Mock(),
            locks=Mock(),
            outbox_publisher=state.publisher,
        )
        start = processor._mark_generating

        def save(session):
            return processor._save_proposal(
                session,
                event,
                proposal_id=str(uuid4()),
                version=1,
                markdown_object_key="late.md",
                draft=Mock(),
            )

    async with state.factory() as session:
        assert await start(session, event) is None
        with pytest.raises(DealFlowError):
            await save(session)
        await processor._mark_failed(session, event, RuntimeError("late failure"))
    async with state.factory() as session:
        assert (await session.get(RFP, state.rfp_id)).status == "ARCHIVED"
        assert (await session.get(Document, state.document_id)).status == "READY"
        assert (
            await session.scalars(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == state.rfp_id)
            )
        ).all() == []
    state.publisher.publish_event.assert_not_awaited()


async def test_customer_deleted_during_file_upload_cannot_gain_new_rfp(retry_state):
    state = retry_state
    async with state.factory() as session:
        customer_id = (await session.get(RFP, state.rfp_id)).customer_id
        await session.rollback()
        await service(state, session).delete(state.rfp_id)

    async def upload(*args, **kwargs):
        async with state.factory() as session:
            await CustomerService(session).delete(customer_id)
        return StoredObject(
            bucket="test",
            object_key="new-upload",
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1,
            checksum_sha256="0" * 64,
        )

    storage = SimpleNamespace(upload_rfp=AsyncMock(side_effect=upload), remove=AsyncMock())
    async with state.factory() as session:
        creator = RFPService(state.settings, session, storage, state.publisher)
        command = CreateRFPCommand(
            customer_id=customer_id,
            title="Late upload",
            reference_number=None,
            priority="NORMAL",
            source_language=None,
            due_at=None,
        )
        with pytest.raises(CustomerNotFoundError):
            await creator.create(command, Mock())
    storage.remove.assert_awaited_once_with("test", "new-upload")
    state.publisher.publish_event.assert_not_awaited()
    async with state.factory() as session:
        active = (
            await session.scalars(
                select(RFP).where(RFP.customer_id == customer_id, RFP.deleted_at.is_(None))
            )
        ).all()
        assert active == []
