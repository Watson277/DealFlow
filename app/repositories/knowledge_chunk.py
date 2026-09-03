from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeChildIndexRecord, KnowledgeChunkRecord
from app.models.mixins import generate_uuid
from app.rag.hierarchical import ParentChunk
from app.rag.incremental import ChildDecision, ExistingChild
from app.repositories.base import BaseRepository


class KnowledgeChunkRepository(BaseRepository[KnowledgeChunkRecord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, KnowledgeChunkRecord)

    async def replace_parents(
        self,
        document_id: str,
        parents: Sequence[ParentChunk],
    ) -> None:
        await self.session.execute(
            delete(KnowledgeChunkRecord).where(
                KnowledgeChunkRecord.document_id == document_id,
                KnowledgeChunkRecord.chunk_level == "PARENT",
            )
        )
        self.session.add_all(
            [
                KnowledgeChunkRecord(
                    id=parent.chunk_id,
                    document_id=document_id,
                    chunk_level="PARENT",
                    chunk_order=parent.order,
                    text=parent.text,
                    source_type=parent.location.source_type,
                    section_path=list(parent.section_path),
                    location=parent.location.model_dump(mode="json"),
                    source_node_ids=list(parent.source_node_ids),
                    block_types=list(parent.block_types),
                    char_count=parent.char_count,
                    token_count=parent.token_count,
                    content_hash=parent.content_hash,
                )
                for parent in parents
            ]
        )

    async def get_parents(self, parent_ids: Sequence[str]) -> dict[str, KnowledgeChunkRecord]:
        unique_ids = list(dict.fromkeys(parent_ids))
        if not unique_ids:
            return {}
        statement = select(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.id.in_(unique_ids),
            KnowledgeChunkRecord.chunk_level == "PARENT",
        )
        records = (await self.session.scalars(statement)).all()
        return {record.id: record for record in records}

    async def list_child_indexes(self, document_id: str) -> list[ExistingChild]:
        statement = (
            select(KnowledgeChildIndexRecord)
            .where(KnowledgeChildIndexRecord.document_id == document_id)
            .order_by(KnowledgeChildIndexRecord.chunk_order)
        )
        records = (await self.session.scalars(statement)).all()
        return [
            ExistingChild(
                child_chunk_id=record.child_chunk_id,
                parent_id=record.parent_id,
                qdrant_point_id=record.qdrant_point_id,
                chunk_order=record.chunk_order,
                child_order=record.child_order,
                structural_hash=record.structural_hash,
                content_hash=record.content_hash,
                embedding_hash=record.embedding_hash,
            )
            for record in records
        ]

    async def replace_child_indexes(
        self,
        document_id: str,
        decisions: Sequence[ChildDecision],
        point_ids: dict[str, str],
    ) -> None:
        await self.session.execute(
            delete(KnowledgeChildIndexRecord).where(
                KnowledgeChildIndexRecord.document_id == document_id
            )
        )
        self.session.add_all(
            [
                KnowledgeChildIndexRecord(
                    id=generate_uuid(),
                    document_id=document_id,
                    child_chunk_id=decision.candidate.chunk.chunk_id,
                    parent_id=decision.candidate.chunk.parent_id,
                    qdrant_point_id=point_ids[decision.candidate.chunk.chunk_id],
                    chunk_order=decision.candidate.chunk.order,
                    child_order=decision.candidate.chunk.child_order,
                    structural_hash=decision.candidate.structural_hash,
                    content_hash=decision.candidate.chunk.content_hash,
                    embedding_hash=decision.candidate.embedding_hash,
                )
                for decision in decisions
            ]
        )
