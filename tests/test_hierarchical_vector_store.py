from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.rag.hierarchical import (
    ChildChunk,
    MarkdownSourceLocation,
    ParentChunk,
)
from app.rag.vector_store import QdrantKnowledgeStore


async def test_vector_search_expands_child_to_parent_and_deduplicates(monkeypatch) -> None:
    client = AsyncQdrantClient(":memory:")
    monkeypatch.setattr("app.rag.vector_store.AsyncQdrantClient", lambda **kwargs: client)
    store = QdrantKnowledgeStore(
        Settings(_env_file=None, qdrant_score_threshold=None, qdrant_search_top_k=5)
    )
    location = MarkdownSourceLocation(
        line_start=3,
        line_end=8,
        block_ids=("md_b0001", "md_b0002"),
    )
    parent = ParentChunk(
        chunk_id="6754980f-258e-50fd-a9f9-c35683ac83f2",
        document_id="knowledge-1",
        text="SAML 2.0 is supported. Audit logs are retained for 180 days.",
        section_path=("Security",),
        order=0,
        source_node_ids=("md_b0001", "md_b0002"),
        block_types=("paragraph",),
        location=location,
        char_count=60,
        content_hash="a" * 64,
    )
    children = [
        ChildChunk(
            chunk_id="ccbe5db1-e88c-5cd4-8a46-e4305581f67d",
            parent_id=parent.chunk_id,
            document_id="knowledge-1",
            text="SAML 2.0 is supported.",
            embedding_text="Section: Security\n\nSAML 2.0 is supported.",
            section_path=("Security",),
            order=0,
            child_order=0,
            source_node_ids=("md_b0001",),
            block_types=("paragraph",),
            location=location,
            char_count=22,
            content_hash="b" * 64,
        ),
        ChildChunk(
            chunk_id="2fb1c948-0fab-5a3e-98ec-5d6e637f9292",
            parent_id=parent.chunk_id,
            document_id="knowledge-1",
            text="Audit logs are retained for 180 days.",
            embedding_text="Section: Security\n\nAudit logs are retained for 180 days.",
            section_path=("Security",),
            order=1,
            child_order=1,
            source_node_ids=("md_b0002",),
            block_types=("paragraph",),
            location=location,
            char_count=37,
            content_hash="c" * 64,
        ),
    ]
    try:
        await store.index_document(
            document_id="knowledge-1",
            title="Security Guide",
            version="1.0",
            category="security",
            chunks=children,
            vectors=[[1.0, 0.0], [0.95, 0.05]],
            parents={parent.chunk_id: parent},
        )

        evidence = await store.search([1.0, 0.0])

        assert len(evidence) == 1
        assert evidence[0].text == parent.text
        assert evidence[0].matched_child_text == children[0].text
        assert evidence[0].parent_id == parent.chunk_id
        assert evidence[0].source_type == "markdown"
        assert evidence[0].location == location.model_dump(mode="json")
    finally:
        await store.close()
