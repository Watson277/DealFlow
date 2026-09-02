from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.vector_store import RetrievedEvidence
from app.repositories import DocumentRepository, KnowledgeChunkRepository


async def expand_parent_evidence(
    session: AsyncSession,
    evidence: list[RetrievedEvidence],
    *,
    limit: int,
) -> list[RetrievedEvidence]:
    """Filter inactive documents and expand retrieved Child text from MySQL Parents."""

    if not evidence or limit < 1:
        return []
    active_ids = await DocumentRepository(session).active_knowledge_ids(
        list(dict.fromkeys(item.document_id for item in evidence))
    )
    active_evidence = [item for item in evidence if item.document_id in active_ids]
    parent_ids = [item.parent_id for item in active_evidence if item.parent_id is not None]
    parents = await KnowledgeChunkRepository(session).get_parents(parent_ids)

    expanded: list[RetrievedEvidence] = []
    seen_parents: set[tuple[str, str]] = set()
    for item in active_evidence:
        if item.parent_id is None:
            expanded.append(item)
        else:
            parent_key = (item.document_id, item.parent_id)
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            parent = parents.get(item.parent_id)
            expanded.append(
                replace(
                    item,
                    text=parent.text if parent is not None else item.text,
                    matched_child_text=item.text if parent is not None else None,
                )
            )
        if len(expanded) >= limit:
            break
    return expanded
