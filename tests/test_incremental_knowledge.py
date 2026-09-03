import hashlib

from app.rag.hierarchical import ChildChunk, MarkdownSourceLocation
from app.rag.incremental import (
    ExistingChild,
    candidates_for,
    classify_children,
    document_content_hash,
)


def _chunk(
    chunk_id: str,
    text: str,
    order: int,
    *,
    section: str = "Security",
) -> ChildChunk:
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    return ChildChunk(
        chunk_id=chunk_id,
        parent_id=f"parent-{section}",
        document_id="document-1",
        text=text,
        embedding_text=f"Section: {section}\n\n{text}",
        section_path=(section,),
        order=order,
        child_order=order,
        source_node_ids=(f"node-{order}",),
        block_types=("paragraph",),
        location=MarkdownSourceLocation(
            line_start=order + 1,
            line_end=order + 1,
            block_ids=(f"node-{order}",),
        ),
        char_count=len(text),
        token_count=4,
        embedding_token_count=7,
        content_hash=content_hash,
    )


def _existing(candidate, point_id: str) -> ExistingChild:
    chunk = candidate.chunk
    return ExistingChild(
        child_chunk_id=chunk.chunk_id,
        parent_id=chunk.parent_id,
        qdrant_point_id=point_id,
        chunk_order=chunk.order,
        child_order=chunk.child_order,
        structural_hash=candidate.structural_hash,
        content_hash=chunk.content_hash,
        embedding_hash=candidate.embedding_hash,
    )


def test_document_hash_normalizes_unicode_line_endings_and_blank_lines() -> None:
    left = "ＡＢＣ  \r\n\r\n\r\n能力说明\r\n"
    right = "ABC\n\n能力说明"

    assert document_content_hash(left) == document_content_hash(right)


def test_child_diff_classifies_retained_changed_added_and_deleted() -> None:
    old_chunks = [
        _chunk("stable", "SAML is supported.", 0),
        _chunk("moved-old", "Audit logs are retained.", 1),
        _chunk("modified", "Retention is 90 days.", 2),
        _chunk("deleted", "Legacy FTP is supported.", 3, section="Legacy"),
    ]
    old_candidates = candidates_for(old_chunks, model="embedding-3", dimensions=1024)
    previous = [
        _existing(candidate, f"point-{index}")
        for index, candidate in enumerate(old_candidates)
    ]
    current = candidates_for(
        [
            _chunk("stable", "SAML is supported.", 0),
            _chunk("moved-new", "Audit logs are retained.", 1),
            _chunk("modified", "Retention is 180 days.", 2),
            _chunk("added", "SCIM provisioning is supported.", 3, section="Identity"),
        ],
        model="embedding-3",
        dimensions=1024,
    )

    changes = classify_children(previous, current)

    assert [decision.kind for decision in changes.decisions] == [
        "UNCHANGED",
        "MOVED",
        "MODIFIED",
        "ADDED",
    ]
    assert [item.child_chunk_id for item in changes.deleted] == ["deleted"]
    assert changes.decisions[1].previous is not None
    assert changes.decisions[1].previous.qdrant_point_id == "point-1"
