from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.models.enums import CapabilityStatus
from app.rag.chunking import KnowledgeChunk, KnowledgeChunker
from app.rag.vector_store import QdrantKnowledgeStore
from app.services.capability_processing import CapabilityProcessingService


def test_knowledge_chunker_preserves_pdf_pages() -> None:
    chunker = KnowledgeChunker(
        Settings(
            knowledge_chunk_size_chars=50,
            knowledge_chunk_overlap_chars=5,
        )
    )

    chunks = chunker.split(
        "--- Page 1 ---\nSAML capability text.\n\n--- Page 2 ---\nDeployment capability text."
    )

    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert chunks[0].text == "SAML capability text."
    assert chunks[1].text == "Deployment capability text."


def test_knowledge_chunker_validates_overlap() -> None:
    with pytest.raises(KnowledgeIndexError, match="OVERLAP"):
        KnowledgeChunker(
            Settings(
                knowledge_chunk_size_chars=100,
                knowledge_chunk_overlap_chars=100,
            )
        )


def test_capability_without_evidence_requires_review() -> None:
    judgment = CapabilityProcessingService._no_evidence_judgment()

    assert judgment.status == CapabilityStatus.NEED_REVIEW
    assert judgment.confidence == 0
    assert judgment.selected_evidence_point_ids == []


@pytest.mark.parametrize("collection_exists", [True, False])
async def test_delete_vectors_targets_only_document_in_original_collection(
    monkeypatch, collection_exists
):
    client = SimpleNamespace(
        collection_exists=AsyncMock(return_value=collection_exists),
        delete=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr("app.rag.vector_store.AsyncQdrantClient", lambda **kwargs: client)
    store = QdrantKnowledgeStore(Settings(_env_file=None, qdrant_collection="new-collection"))
    await store.delete_document("document-to-delete", collection_name="original-collection")
    client.collection_exists.assert_awaited_once_with("original-collection")
    if collection_exists:
        kwargs = client.delete.call_args.kwargs
        assert kwargs["collection_name"] == "original-collection"
        assert kwargs["wait"] is True
        conditions = kwargs["points_selector"].must
        assert len(conditions) == 1
        assert conditions[0].key == "document_id"
        assert conditions[0].match.value == "document-to-delete"
    else:
        client.delete.assert_not_awaited()


async def test_deleted_document_disappears_from_vector_search_without_affecting_others(monkeypatch):
    client = AsyncQdrantClient(":memory:")
    monkeypatch.setattr("app.rag.vector_store.AsyncQdrantClient", lambda **kwargs: client)
    store = QdrantKnowledgeStore(Settings(_env_file=None, qdrant_score_threshold=None))
    try:
        for document_id in ["delete-me", "keep-me"]:
            await store.index_document(
                document_id=document_id,
                title=document_id,
                version=None,
                category="test",
                chunks=[KnowledgeChunk(chunk_index=0, text="SAML support", page_number=None)],
                vectors=[[1.0, 0.0, 0.0]],
            )
        assert {item.document_id for item in await store.search([1.0, 0.0, 0.0])} == {
            "delete-me",
            "keep-me",
        }
        await store.delete_document("delete-me")
        assert {item.document_id for item in await store.search([1.0, 0.0, 0.0])} == {"keep-me"}
    finally:
        await store.close()
