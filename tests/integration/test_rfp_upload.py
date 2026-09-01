import asyncio
import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.main import app
from app.models import RFP, Customer, Document, OutboxEvent, WorkflowRun
from app.models.enums import OutboxStatus, RFPStatus
from app.services.kafka import get_kafka_service
from app.services.storage import ObjectStorageService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run infrastructure integration tests",
    ),
]


@pytest.mark.asyncio
async def test_post_rfps_persists_file_and_publishes_event() -> None:
    settings = get_settings()
    suffix = uuid4().hex
    customer_id = str(uuid4())
    rfp_id: str | None = None
    object_key: str | None = None
    storage = ObjectStorageService(settings)

    async with async_session_factory() as session, session.begin():
        session.add(
            Customer(
                id=customer_id,
                name="RFP Upload Integration Customer",
                code=f"UPLOAD-{suffix[:12]}",
                extra_data={},
            )
        )

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/rfps",
                data={
                    "customer_id": customer_id,
                    "title": "Integration Test RFP Upload",
                    "reference_number": f"REF-{suffix[:12]}",
                    "priority": "NORMAL",
                    "source_language": "en-US",
                },
                files={
                    "file": (
                        "customer-rfp.pdf",
                        b"%PDF-1.7\nDealFlow integration test RFP\n%%EOF",
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == RFPStatus.QUEUED.value
        assert body["event_status"] == OutboxStatus.PUBLISHED.value
        rfp_id = body["rfp_id"]

        async with async_session_factory() as verification_session, verification_session.begin():
            persisted_event = await verification_session.scalar(
                select(OutboxEvent).where(OutboxEvent.id == body["event_id"])
            )
            persisted_document = await verification_session.scalar(
                select(Document).where(Document.id == body["document_id"])
            )

        assert persisted_event is not None
        assert persisted_event.status == OutboxStatus.PUBLISHED.value
        assert persisted_event.published_at is not None
        assert persisted_document is not None
        assert persisted_document.checksum_sha256
        object_key = persisted_document.object_key

        stat = await asyncio.to_thread(
            storage.client.stat_object,
            settings.minio_bucket,
            object_key,
        )
        assert stat.size > 0
    finally:
        await get_kafka_service().stop()
        if object_key is not None:
            await storage.remove(settings.minio_bucket, object_key)

        async with async_session_factory() as cleanup_session, cleanup_session.begin():
            if rfp_id is not None:
                await cleanup_session.execute(
                    delete(OutboxEvent).where(OutboxEvent.aggregate_id == rfp_id)
                )
                await cleanup_session.execute(delete(Document).where(Document.rfp_id == rfp_id))
                await cleanup_session.execute(
                    delete(WorkflowRun).where(WorkflowRun.rfp_id == rfp_id)
                )
                await cleanup_session.execute(delete(RFP).where(RFP.id == rfp_id))
            await cleanup_session.execute(delete(Customer).where(Customer.id == customer_id))

        await engine.dispose()
