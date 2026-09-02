from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document


class KnowledgeChunkRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted knowledge chunk content; currently only Parent chunks are stored."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_level",
            "chunk_order",
            name="uq_knowledge_chunks_document_level_order",
        ),
        CheckConstraint("chunk_order >= 0", name="chunk_order_nonnegative"),
        CheckConstraint("char_count > 0", name="char_count_positive"),
        CheckConstraint(
            "chunk_level IN ('PARENT', 'CHILD')",
            name="chunk_level_valid",
        ),
        Index("ix_knowledge_chunks_document_level", "document_id", "chunk_level"),
        Index("ix_knowledge_chunks_content_hash", "content_hash"),
    )

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PARENT",
        server_default="PARENT",
    )
    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    section_path: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    location: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    source_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    block_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    document: Mapped[Document] = relationship(back_populates="knowledge_chunks")
