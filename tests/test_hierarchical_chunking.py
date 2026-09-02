from uuid import uuid4

from app.core.config import Settings
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
from app.rag.hierarchical import (
    HierarchicalKnowledgeChunker,
    KnowledgeChunkBundle,
    MarkdownSourceLocation,
    MarkdownStructureAdapter,
    PDFSourceLocation,
    PDFStructureAdapter,
    serialize_knowledge_chunks,
)


def _settings(*, parent_size: int = 300, child_size: int = 100) -> Settings:
    return Settings(
        _env_file=None,
        knowledge_parent_chunk_size_chars=parent_size,
        knowledge_child_chunk_size_chars=child_size,
        knowledge_child_overlap_chars=10,
    )


def _block(
    block_id: str,
    block_type: PDFBlockType,
    order: int,
    *,
    text: str | None = None,
    table_markdown: str | None = None,
    heading_level: int | None = None,
) -> BlockIR:
    return BlockIR(
        block_id=block_id,
        type=block_type,
        bbox=BoundingBox(x0=10, y0=10 + order * 25, x1=500, y1=30 + order * 25),
        source=PDFBlockSource.NATIVE,
        reading_order=order,
        text=text,
        table_markdown=table_markdown,
        metadata={"heading_level": heading_level} if heading_level is not None else {},
    )


def _pdf_document(*blocks: BlockIR) -> DocumentIR:
    return DocumentIR(
        parser_version="hierarchical-test",
        document_id=uuid4(),
        source_filename="knowledge.pdf",
        checksum_sha256="0" * 64,
        document_type=PDFDocumentType.TEXT_BASED,
        page_count=1,
        pages=(
            PageIR(
                page_number=1,
                width=600,
                height=800,
                page_type=PDFPageType.TEXT,
                blocks=blocks,
            ),
        ),
    )


def test_pdf_and_markdown_share_one_hierarchical_output_schema() -> None:
    pdf_id = str(uuid4())
    pdf = _pdf_document(
        _block("title", PDFBlockType.TITLE, 0, text="Security", heading_level=1),
        _block("text", PDFBlockType.TEXT, 1, text="SAML 2.0 is supported."),
        _block("list", PDFBlockType.LIST, 2, text="- OIDC\n- SCIM"),
    )
    pdf_structure = PDFStructureAdapter.convert(
        pdf,
        document_id=pdf_id,
        title="PDF Guide",
        version="1.0",
    )
    markdown_id = str(uuid4())
    markdown_structure = MarkdownStructureAdapter.convert(
        "# Security\n\nSAML 2.0 is supported.\n\n- OIDC\n- SCIM\n",
        document_id=markdown_id,
        title="Markdown Guide",
        version="1.0",
    )
    chunker = HierarchicalKnowledgeChunker(_settings())

    pdf_bundle = chunker.split(pdf_structure)
    markdown_bundle = chunker.split(markdown_structure)

    assert isinstance(pdf_bundle.parents[0].location, PDFSourceLocation)
    assert pdf_bundle.parents[0].location.page_start == 1
    assert pdf_bundle.parents[0].location.bboxes
    assert isinstance(markdown_bundle.parents[0].location, MarkdownSourceLocation)
    assert markdown_bundle.parents[0].location.line_start == 3
    assert markdown_bundle.parents[0].location.line_end == 6
    assert pdf_bundle.model_dump().keys() == markdown_bundle.model_dump().keys()
    assert all(child.parent_id == pdf_bundle.parents[0].chunk_id for child in pdf_bundle.children)
    assert all(
        child.parent_id == markdown_bundle.parents[0].chunk_id
        for child in markdown_bundle.children
    )


def test_child_embedding_context_is_separate_from_original_text() -> None:
    document = MarkdownStructureAdapter.convert(
        "# Security\n\nSAML 2.0 is supported.\n",
        document_id=str(uuid4()),
        title="Identity Guide",
        version="3.2",
    )

    child = HierarchicalKnowledgeChunker(_settings()).split(document).children[0]

    assert child.text == "SAML 2.0 is supported."
    assert child.embedding_text == (
        "Document: Identity Guide\n"
        "Version: 3.2\n"
        "Section: Security\n\n"
        "SAML 2.0 is supported."
    )


def test_markdown_table_is_one_parent_and_children_repeat_header() -> None:
    markdown = (
        "# Products\n\n"
        "| Product | Capability |\n"
        "| --- | --- |\n"
        "| Enterprise | SAML 2.0 |\n"
        "| Business | OIDC |\n"
        "| Community | Password only |\n"
    )
    document = MarkdownStructureAdapter.convert(
        markdown,
        document_id=str(uuid4()),
        title="Products",
        version=None,
    )

    bundle = HierarchicalKnowledgeChunker(
        _settings(parent_size=300, child_size=100)
    ).split(document)

    assert len(bundle.parents) == 1
    assert len(bundle.children) > 1
    assert bundle.parents[0].block_types == ("table",)
    assert all(
        child.text.startswith("| Product | Capability |\n| --- | --- |")
        for child in bundle.children
    )


def test_parent_ids_are_scoped_to_document() -> None:
    first = MarkdownStructureAdapter.convert(
        "# Security\n\nSAML is supported.",
        document_id=str(uuid4()),
        title=None,
        version=None,
    )
    second = first.model_copy(update={"document_id": str(uuid4())})
    chunker = HierarchicalKnowledgeChunker(_settings())

    first_parent = chunker.split(first).parents[0]
    second_parent = chunker.split(second).parents[0]

    assert first_parent.chunk_id != second_parent.chunk_id


def test_chunk_bundle_json_round_trips() -> None:
    document = MarkdownStructureAdapter.convert(
        "# Security\n\nAudit logs are retained.",
        document_id=str(uuid4()),
        title="Operations",
        version="2.0",
    )
    bundle = HierarchicalKnowledgeChunker(_settings()).split(document)

    restored = KnowledgeChunkBundle.model_validate_json(serialize_knowledge_chunks(bundle))

    assert restored == bundle
