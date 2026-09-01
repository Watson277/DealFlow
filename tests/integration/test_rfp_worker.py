import asyncio
import os
from uuid import uuid4

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.infrastructure.messaging.kafka import get_kafka_service
from app.infrastructure.storage.minio import ObjectStorageService
from app.main import app
from app.models import RFP, Customer, Document, OutboxEvent, Requirement, WorkflowRun
from app.models.enums import DocumentStatus, OutboxStatus, RFPStatus, WorkflowStatus
from app.schemas.requirement import ExtractedRequirement
from app.workers.requirement_worker import RequirementWorker
from app.workers.rfp_worker import RFPWorker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run infrastructure integration tests",
    ),
]


def _build_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "DealFlow worker integration requirement")
    content = document.tobytes()
    document.close()
    return content


class FakeRequirementExtractor:
    async def extract(
        self,
        document_text: str,
        *,
        rfp_id: str,
        title: str,
    ) -> list[ExtractedRequirement]:
        assert "--- Page 1 ---" in document_text
        assert rfp_id
        assert title == "Worker Integration RFP"
        return [
            ExtractedRequirement(
                category="security",
                requirement_text="The solution must support SAML 2.0.",
                normalized_text="Support SAML 2.0",
                mandatory=True,
                source_page_start=1,
                source_page_end=1,
                source_quote="must support SAML 2.0",
                confidence=0.98,
            ),
            ExtractedRequirement(
                category="security",
                requirement_text="SAML 2.0 is required.",
                normalized_text="Support  SAML 2.0",
                mandatory=True,
                source_page_start=1,
                source_page_end=1,
                source_quote="SAML 2.0",
                confidence=0.80,
            ),
            ExtractedRequirement(
                category="deployment",
                requirement_text="Deployment must complete within 30 days.",
                normalized_text="Complete deployment within 30 days",
                mandatory=True,
                source_page_start=1,
                source_page_end=1,
                source_quote="within 30 days",
                confidence=0.95,
            ),
        ]


@pytest.mark.asyncio
async def test_worker_processes_uploaded_rfp_and_query_endpoints() -> None:
    settings = get_settings()
    suffix = uuid4().hex
    customer_id = str(uuid4())
    rfp_id: str | None = None
    source_key: str | None = None
    parsed_key: str | None = None
    storage = ObjectStorageService(settings)
    worker_settings = settings.model_copy(
        update={
            "kafka_rfp_worker_group": f"dealflow-rfp-test-{suffix}",
            "kafka_requirement_worker_group": f"dealflow-requirement-test-{suffix}",
        }
    )
    worker = RFPWorker(worker_settings)
    requirement_worker = RequirementWorker(
        worker_settings,
        extractor=FakeRequirementExtractor(),
    )
    worker_task = asyncio.create_task(worker.run())
    requirement_worker_task = asyncio.create_task(requirement_worker.run())

    async with async_session_factory() as session, session.begin():
        session.add(
            Customer(
                id=customer_id,
                name="RFP Worker Integration Customer",
                code=f"WORKER-{suffix[:12]}",
                extra_data={},
            )
        )

    try:
        await asyncio.wait_for(worker.started.wait(), timeout=15)
        await asyncio.wait_for(requirement_worker.started.wait(), timeout=15)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/rfps",
                data={
                    "customer_id": customer_id,
                    "title": "Worker Integration RFP",
                    "reference_number": f"WORKER-REF-{suffix[:12]}",
                },
                files={"file": ("worker-rfp.pdf", _build_pdf(), "application/pdf")},
            )
            assert response.status_code == 202, response.text
            body = response.json()
            assert body["event_status"] == OutboxStatus.PUBLISHED.value
            rfp_id = body["rfp_id"]

            deadline = asyncio.get_running_loop().time() + 20
            status_body: dict[str, object] = {}
            while asyncio.get_running_loop().time() < deadline:
                status_response = await client.get(f"/rfps/{rfp_id}/status")
                assert status_response.status_code == 200, status_response.text
                status_body = status_response.json()
                if (
                    status_body["current_stage"] == "requirements_extracted"
                    or status_body["status"] == RFPStatus.FAILED.value
                ):
                    break
                await asyncio.sleep(0.25)

            assert status_body["status"] == RFPStatus.PROCESSING.value, status_body
            assert status_body["current_stage"] == "requirements_extracted"

            detail_response = await client.get(f"/rfps/{rfp_id}")
            assert detail_response.status_code == 200, detail_response.text
            detail = detail_response.json()
            assert detail["documents"][0]["status"] == DocumentStatus.READY.value
            assert detail["documents"][0]["page_count"] == 1
            assert detail["workflow_runs"][0]["status"] == WorkflowStatus.RUNNING.value
            assert detail["workflow_runs"][0]["current_node"] == "capability_agent"
            parsed_key = detail["documents"][0]["parsed_text_object_key"]

            requirements_response = await client.get(f"/rfps/{rfp_id}/requirements")
            assert requirements_response.status_code == 200, requirements_response.text
            requirements = requirements_response.json()
            assert requirements["total"] == 2
            assert [item["requirement_key"] for item in requirements["items"]] == [
                "REQ-0001",
                "REQ-0002",
            ]
            assert requirements["items"][0]["normalized_text"] == "Support SAML 2.0"
            assert requirements["items"][0]["mandatory"] is True

            list_response = await client.get(
                "/rfps",
                params={
                    "customer_id": customer_id,
                    "status": RFPStatus.PROCESSING.value,
                    "search": "Worker Integration",
                },
            )
            assert list_response.status_code == 200, list_response.text
            listing = list_response.json()
            assert listing["total"] == 1
            assert listing["items"][0]["id"] == rfp_id

        assert parsed_key is not None
        parsed_text = await storage.download(settings.minio_bucket, parsed_key)
        assert b"DealFlow worker integration requirement" in parsed_text

        async with async_session_factory() as session, session.begin():
            document = await session.scalar(select(Document).where(Document.rfp_id == rfp_id))
            assert document is not None
            source_key = document.object_key
            completed_event = await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == rfp_id,
                    OutboxEvent.topic == settings.kafka_rfp_completed_topic,
                )
            )
            assert completed_event is not None
            assert completed_event.status == OutboxStatus.PUBLISHED.value
            extracted_event = await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == rfp_id,
                    OutboxEvent.topic == settings.kafka_requirements_extracted_topic,
                )
            )
            assert extracted_event is not None
            assert extracted_event.status == OutboxStatus.PUBLISHED.value
    finally:
        worker.request_stop()
        requirement_worker.request_stop()
        await asyncio.wait_for(
            asyncio.gather(worker_task, requirement_worker_task),
            timeout=10,
        )
        await get_kafka_service().stop()
        if rfp_id is not None and source_key is None:
            async with async_session_factory() as lookup_session, lookup_session.begin():
                document = await lookup_session.scalar(
                    select(Document).where(Document.rfp_id == rfp_id)
                )
                if document is not None:
                    source_key = document.object_key
                    parsed_key = parsed_key or document.parsed_text_object_key
        for object_key in (source_key, parsed_key):
            if object_key is not None:
                await storage.remove(settings.minio_bucket, object_key)

        async with async_session_factory() as cleanup_session, cleanup_session.begin():
            if rfp_id is not None:
                await cleanup_session.execute(
                    delete(OutboxEvent).where(OutboxEvent.aggregate_id == rfp_id)
                )
                await cleanup_session.execute(
                    delete(Requirement).where(Requirement.rfp_id == rfp_id)
                )
                await cleanup_session.execute(delete(Document).where(Document.rfp_id == rfp_id))
                await cleanup_session.execute(
                    delete(WorkflowRun).where(WorkflowRun.rfp_id == rfp_id)
                )
                await cleanup_session.execute(delete(RFP).where(RFP.id == rfp_id))
            await cleanup_session.execute(delete(Customer).where(Customer.id == customer_id))

        await engine.dispose()
