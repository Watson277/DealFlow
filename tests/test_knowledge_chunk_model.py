from app.models import Document, KnowledgeChunkRecord


def test_knowledge_chunk_table_has_parent_persistence_columns() -> None:
    table = KnowledgeChunkRecord.__table__

    assert table.name == "knowledge_chunks"
    assert {
        "id",
        "document_id",
        "chunk_level",
        "chunk_order",
        "text",
        "source_type",
        "section_path",
        "location",
        "source_node_ids",
        "block_types",
        "char_count",
        "content_hash",
        "created_at",
        "updated_at",
    }.issubset(table.columns.keys())
    assert Document.knowledge_chunks.property.mapper.class_ is KnowledgeChunkRecord
