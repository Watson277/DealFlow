from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.models.enums import DocumentStatus, DocumentType
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Document)

    async def get_rfp_source(self, rfp_id: str) -> Document | None:
        statement = select(Document).where(
            Document.rfp_id == rfp_id,
            Document.document_type == DocumentType.RFP_SOURCE.value,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_knowledge(self, *, offset: int, limit: int) -> list[Document]:
        statement = (
            select(Document)
            .where(
                Document.document_type == DocumentType.KNOWLEDGE.value,
                Document.status != DocumentStatus.ARCHIVED.value,
            )
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def count_knowledge(self) -> int:
        statement = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.document_type == DocumentType.KNOWLEDGE.value,
                Document.status != DocumentStatus.ARCHIVED.value,
            )
        )
        return int((await self.session.scalar(statement)) or 0)

    async def get_knowledge(self, document_id: str) -> Document | None:
        statement = select(Document).where(
            Document.id == document_id,
            Document.document_type == DocumentType.KNOWLEDGE.value,
            Document.status != DocumentStatus.ARCHIVED.value,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_knowledge_for_update(self, document_id: str) -> Document | None:
        statement = (
            select(Document)
            .where(
                Document.id == document_id,
                Document.document_type == DocumentType.KNOWLEDGE.value,
                Document.status != DocumentStatus.ARCHIVED.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def active_knowledge_ids(self, document_ids: list[str]) -> set[str]:
        statement = select(Document.id).where(
            Document.id.in_(document_ids),
            Document.document_type == DocumentType.KNOWLEDGE.value,
            Document.status == DocumentStatus.READY.value,
        )
        return set((await self.session.scalars(statement)).all())

    async def find_active_knowledge_by_content_hash(
        self,
        content_hash: str,
        *,
        exclude_document_id: str | None = None,
    ) -> Document | None:
        statement = select(Document).where(
            Document.document_type == DocumentType.KNOWLEDGE.value,
            Document.status != DocumentStatus.ARCHIVED.value,
            Document.content_hash == content_hash,
        )
        if exclude_document_id is not None:
            statement = statement.where(Document.id != exclude_document_id)
        return (await self.session.scalars(statement.limit(1))).first()

    async def find_active_knowledge_by_checksum(
        self,
        checksum_sha256: str,
    ) -> Document | None:
        statement = select(Document).where(
            Document.document_type == DocumentType.KNOWLEDGE.value,
            Document.status != DocumentStatus.ARCHIVED.value,
            Document.checksum_sha256 == checksum_sha256,
        )
        return (await self.session.scalars(statement.limit(1))).first()
