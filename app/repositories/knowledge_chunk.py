from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeChunkRecord
from app.rag.hierarchical import ParentChunk
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
