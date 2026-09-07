from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.documents.pdf.models import (
    BlockIR,
    BoundingBox,
    DocumentIR,
    PageIR,
    PDFBlockSource,
    PDFBlockType,
    PDFDocumentType,
    PDFPageType,
)
from app.models.enums import CapabilityStatus
from app.rag.chunking import KnowledgeChunk, KnowledgeChunker
from app.rag.vector_store import QdrantKnowledgeStore
from app.workflow.stages.evaluate_capabilities import CapabilityProcessingService


def _block(
    block_id: str,
    block_type: PDFBlockType,
    reading_order: int,
    *,
    text: str | None = None,
    table_markdown: str | None = None,
    heading_level: int | None = None,
) -> BlockIR:
    metadata = {"heading_level": heading_level} if heading_level else {}
    return BlockIR(
        block_id=block_id,
        type=block_type,
        bbox=BoundingBox(x0=10, y0=10 + reading_order * 20, x1=500, y1=25 + reading_order * 20),
        source=PDFBlockSource.NATIVE,
        reading_order=reading_order,
        text=text,
        table_markdown=table_markdown,
        metadata=metadata,
    )


def _document_ir(*pages: PageIR) -> DocumentIR:
    return DocumentIR(
        parser_version="test-parser",
        document_id=uuid4(),
        source_filename="guide.pdf",
        checksum_sha256="0" * 64,
        document_type=PDFDocumentType.TEXT_BASED,
        page_count=len(pages),
        pages=pages,
    )


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


def test_knowledge_chunker_uses_document_ir_structure_and_context() -> None:
    chunker = KnowledgeChunker(
        Settings(knowledge_chunk_size_chars=500, knowledge_chunk_overlap_chars=20)
    )
    document_ir = _document_ir(
        PageIR(
            page_number=1,
            width=600,
            height=800,
            page_type=PDFPageType.TEXT,
            blocks=(
                _block("header", PDFBlockType.HEADER, 0, text="Repeated header"),
                _block(
                    "title-1",
                    PDFBlockType.TITLE,
                    1,
                    text="Security",
                    heading_level=1,
                ),
                _block("text-1", PDFBlockType.TEXT, 2, text="SAML 2.0 is supported."),
                _block("caption-1", PDFBlockType.CAPTION, 3, text="Table 1. SSO support"),
                _block(
                    "table-1",
                    PDFBlockType.TABLE,
                    4,
                    table_markdown="| Tier | SSO |\n| --- | --- |\n| Enterprise | Yes |",
                ),
                _block("footer", PDFBlockType.FOOTER, 5, text="Page 1"),
            ),
        ),
        PageIR(
            page_number=2,
            width=600,
            height=800,
            page_type=PDFPageType.TEXT,
            blocks=(
                _block(
                    "title-2",
                    PDFBlockType.TITLE,
                    0,
                    text="Provisioning",
                    heading_level=2,
                ),
                _block("list-1", PDFBlockType.LIST, 1, text="- SCIM 2.0\n- JIT"),
            ),
        ),
    )

    chunks = chunker.split(
        "ignored compatibility text",
        document_ir=document_ir,
        document_title="Identity Guide",
        document_version="3.2",
    )

    assert len(chunks) == 3
    assert chunks[0].page_number == chunks[0].page_end == 1
    assert chunks[0].section_path == ("Security",)
    assert chunks[0].block_types == ("text",)
    assert chunks[0].source_block_ids == ("text-1",)
    assert chunks[0].parent_id == chunks[1].parent_id
    assert chunks[0].text.startswith(
        "Document: Identity Guide\nVersion: 3.2\nSection: Security\n\n"
    )
    assert "Repeated header" not in "\n".join(chunk.text for chunk in chunks)
    assert "Page 1" not in "\n".join(chunk.text for chunk in chunks)
    assert chunks[1].block_types == ("caption", "table")
    assert "Table 1. SSO support" in chunks[1].text
    assert "| Enterprise | Yes |" in chunks[1].text
    assert chunks[2].section_path == ("Security", "Provisioning")
    assert chunks[2].block_types == ("list",)


def test_knowledge_chunker_splits_large_markdown_tables_by_row_with_header() -> None:
    chunker = KnowledgeChunker(
        Settings(knowledge_chunk_size_chars=70, knowledge_chunk_overlap_chars=5)
    )
    table = (
        "| Product | Capability |\n"
        "| --- | --- |\n"
        "| Enterprise | SAML 2.0 |\n"
        "| Business | OIDC |\n"
        "| Community | Password only |"
    )
    document_ir = _document_ir(
        PageIR(
            page_number=1,
            width=600,
            height=800,
            page_type=PDFPageType.TEXT,
            blocks=(
                _block("table", PDFBlockType.TABLE, 0, table_markdown=table),
            ),
        )
    )

    chunks = chunker.split(table, document_ir=document_ir)

    assert len(chunks) > 1
    assert all(chunk.text.startswith("| Product | Capability |\n| --- | --- |") for chunk in chunks)
    assert sum("Enterprise" in chunk.text for chunk in chunks) == 1
    assert sum("Community" in chunk.text for chunk in chunks) == 1


def test_knowledge_chunker_replaces_peer_headings_instead_of_nesting_them() -> None:
    chunker = KnowledgeChunker(
        Settings(knowledge_chunk_size_chars=500, knowledge_chunk_overlap_chars=20)
    )
    document_ir = _document_ir(
        PageIR(
            page_number=1,
            width=600,
            height=800,
            page_type=PDFPageType.TEXT,
            blocks=(
                _block("title-1", PDFBlockType.TITLE, 0, text="Authentication"),
                _block("text-1", PDFBlockType.TEXT, 1, text="SAML is supported."),
                _block("title-2", PDFBlockType.TITLE, 2, text="Audit"),
                _block("text-2", PDFBlockType.TEXT, 3, text="Audit logs are retained."),
            ),
        )
    )

    chunks = chunker.split("fallback", document_ir=document_ir)

    assert [chunk.section_path for chunk in chunks] == [("Authentication",), ("Audit",)]


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


async def test_vector_store_round_trips_structural_chunk_metadata(monkeypatch) -> None:
    client = AsyncQdrantClient(":memory:")
    monkeypatch.setattr("app.rag.vector_store.AsyncQdrantClient", lambda **kwargs: client)
    store = QdrantKnowledgeStore(Settings(_env_file=None, qdrant_score_threshold=None))
    try:
        await store.index_document(
            document_id="structured-document",
            title="Identity Guide",
            version="3.2",
            category="security",
            chunks=[
                KnowledgeChunk(
                    chunk_index=0,
                    text="Section: Security > SAML\n\nSAML 2.0 is supported.",
                    page_number=4,
                    page_end=5,
                    section_path=("Security", "SAML"),
                    block_types=("text", "list"),
                    source_block_ids=("p4_b1", "p5_b2"),
                    parent_id="section:identity-saml",
                )
            ],
            vectors=[[1.0, 0.0, 0.0]],
        )

        evidence = (await store.search([1.0, 0.0, 0.0]))[0]

        assert evidence.page_number == 4
        assert evidence.page_end == 5
        assert evidence.section_path == ("Security", "SAML")
        assert evidence.block_types == ("text", "list")
        assert evidence.source_block_ids == ("p4_b1", "p5_b2")
        assert evidence.parent_id == "section:identity-saml"
    finally:
        await store.close()
