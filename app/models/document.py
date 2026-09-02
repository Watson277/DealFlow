from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DocumentStatus, DocumentType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.capability import CapabilityEvidence
    from app.models.knowledge_chunk import KnowledgeChunkRecord
    from app.models.requirement import Requirement
    from app.models.rfp import RFP
    from app.models.user import User


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_documents_bucket_object_key"),
        CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        Index("ix_documents_rfp_type", "rfp_id", "document_type"),
        Index("ix_documents_checksum", "checksum_sha256"),
        Index("ix_documents_type_status", "document_type", "status"),
    )

    rfp_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("rfps.id", ondelete="RESTRICT"),
        nullable=True,
    )
    uploaded_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
        server_default=DocumentStatus.UPLOADED.value,
    )
    bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    knowledge_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parsed_text_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parsed_ir_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extra_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    rfp: Mapped[RFP | None] = relationship(back_populates="documents")
    uploaded_by: Mapped[User | None] = relationship(foreign_keys=[uploaded_by_id])
    requirements: Mapped[list[Requirement]] = relationship(back_populates="source_document")
    evidence_items: Mapped[list[CapabilityEvidence]] = relationship(back_populates="document")
    knowledge_chunks: Mapped[list[KnowledgeChunkRecord]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    @property
    def is_knowledge_document(self) -> bool:
        return self.document_type == DocumentType.KNOWLEDGE.value
