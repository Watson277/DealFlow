from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.api.dependencies import get_knowledge_service
from app.infrastructure.storage.minio import StoredObject
from app.main import create_app
from app.models.enums import DocumentStatus
from app.schemas.events import KnowledgeIngestionRequestedEvent
from app.services.knowledge import KnowledgeService


class FakeSession:
    def __init__(self) -> None:
        self.flush = AsyncMock()

    @asynccontextmanager
    async def begin(self):
        yield


@pytest.mark.asyncio
async def test_enqueue_persists_uploaded_document_and_publishes_event(monkeypatch) -> None:
    documents: list[object] = []
    events: list[object] = []

    class FakeDocumentRepository:
        def __init__(self, session) -> None:
            pass

        async def find_active_knowledge_by_checksum(self, checksum):
            return None

        def add(self, document) -> None:
            documents.append(document)

    class FakeOutboxEventRepository:
        def __init__(self, session) -> None:
            pass

        def add(self, event) -> None:
            events.append(event)

    monkeypatch.setattr("app.services.knowledge.DocumentRepository", FakeDocumentRepository)
    monkeypatch.setattr(
        "app.services.knowledge.OutboxEventRepository",
        FakeOutboxEventRepository,
    )
    storage = SimpleNamespace(
        upload_knowledge=AsyncMock(
            return_value=StoredObject(
                bucket="dealflow",
                object_key="knowledge/security/document/guide.md",
                original_filename="guide.md",
                content_type="text/markdown",
                size_bytes=12,
                checksum_sha256="a" * 64,
            )
        ),
        remove=AsyncMock(),
    )
    publisher = SimpleNamespace(publish_event=AsyncMock(return_value="PUBLISHED"))
    vector_store = SimpleNamespace(
        settings=SimpleNamespace(
            kafka_knowledge_ingestion_topic="knowledge.ingestion.requested"
        )
    )
    service = KnowledgeService(
        session=FakeSession(),  # type: ignore[arg-type]
        storage=storage,
        parser=SimpleNamespace(),  # type: ignore[arg-type]
        chunker=SimpleNamespace(),  # type: ignore[arg-type]
        embeddings=SimpleNamespace(),  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        outbox_publisher=publisher,
    )

    document = await service.enqueue_ingestion(
        UploadFile(filename="guide.md", file=BytesIO(b"# Knowledge")),
        title="Security Guide",
        category="Security",
        version="1.0",
    )

    assert document.status == DocumentStatus.UPLOADED.value
    assert document.extra_data["ingestion_stage"] == "QUEUED"
    assert documents == [document]
    assert len(events) == 1
    event = events[0]
    assert event.topic == "knowledge.ingestion.requested"
    assert event.payload["document_id"] == document.id
    publisher.publish_event.assert_awaited_once()
    storage.remove.assert_not_awaited()


def test_knowledge_event_schema_is_strict() -> None:
    event = KnowledgeIngestionRequestedEvent.model_validate(
        {
            "event_id": "event-1",
            "event_type": "knowledge.ingestion.requested",
            "occurred_at": datetime.now(UTC).isoformat(),
            "document_id": "document-1",
        }
    )

    assert event.document_id == "document-1"


def test_create_knowledge_returns_202_queued_response() -> None:
    now = datetime.now(UTC)
    document = SimpleNamespace(
        id="9ff249d1-518e-47d3-9b98-509627eb75b7",
        status=DocumentStatus.UPLOADED.value,
        original_filename="guide.md",
        content_type="text/markdown",
        size_bytes=12,
        content_hash=None,
        page_count=None,
        document_version="1.0",
        knowledge_category="security",
        parsed_text_object_key=None,
        parsed_ir_object_key=None,
        extra_data={"title": "Security Guide", "ingestion_stage": "QUEUED"},
        created_at=now,
        updated_at=now,
    )
    service = SimpleNamespace(
        enqueue_ingestion=AsyncMock(return_value=document),
        close=AsyncMock(),
    )
    app = create_app()
    app.dependency_overrides[get_knowledge_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/knowledge",
            data={"title": "Security Guide", "category": "security", "version": "1.0"},
            files={"file": ("guide.md", b"# Knowledge", "text/markdown")},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "UPLOADED"
    assert response.json()["extra_data"]["ingestion_stage"] == "QUEUED"
    service.enqueue_ingestion.assert_awaited_once()
    service.close.assert_awaited_once()
