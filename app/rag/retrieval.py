from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.vector_store import RetrievedEvidence
from app.repositories import DocumentRepository, KnowledgeChunkRepository


def group_child_evidence(
    evidence: list[RetrievedEvidence],
) -> list[RetrievedEvidence]:
    """Keep the highest-ranked Child hit for each Parent without reordering results."""

    grouped: list[RetrievedEvidence] = []
    seen: set[tuple[str, str, str]] = set()
    for item in evidence:
        if item.parent_id is not None:
            key = ("parent", item.document_id, item.parent_id)
        else:
            key = ("point", item.document_id, item.point_id)
        if key in seen:
            continue
        seen.add(key)
        grouped.append(item)
    return grouped


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
    active_evidence = group_child_evidence(
        [item for item in evidence if item.document_id in active_ids]
    )
    parent_ids = list(
        dict.fromkeys(
            item.parent_id for item in active_evidence if item.parent_id is not None
        )
    )
    parents = await KnowledgeChunkRepository(session).get_parents(parent_ids)

    expanded: list[RetrievedEvidence] = []
    for item in active_evidence:
        parent = parents.get(item.parent_id) if item.parent_id is not None else None
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
