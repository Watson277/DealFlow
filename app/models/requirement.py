from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.capability import CapabilityResult
    from app.models.document import Document
    from app.models.rfp import RFP


class Requirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("rfp_id", "requirement_key", name="uq_requirements_rfp_key"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_requirements_rfp_category", "rfp_id", "category"),
        Index("ix_requirements_rfp_mandatory", "rfp_id", "mandatory"),
        Index("ix_requirements_fingerprint", "fingerprint"),
    )

    rfp_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rfps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_requirement_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("requirements.id", ondelete="SET NULL"),
        nullable=True,
    )
    requirement_key: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    mandatory: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    source_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_output: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    rfp: Mapped[RFP] = relationship(back_populates="requirements")
    source_document: Mapped[Document] = relationship(back_populates="requirements")
    parent: Mapped[Requirement | None] = relationship(
        back_populates="children",
        remote_side="Requirement.id",
    )
    children: Mapped[list[Requirement]] = relationship(back_populates="parent")
    capability_results: Mapped[list[CapabilityResult]] = relationship(back_populates="requirement")
