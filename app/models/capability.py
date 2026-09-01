from __future__ import annotations

from datetime import datetime
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
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.requirement import Requirement
    from app.models.user import User
    from app.models.workflow import WorkflowRun


class CapabilityResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "capability_results"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id",
            "workflow_run_id",
            name="uq_capability_results_requirement_run",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_capability_results_requirement_created", "requirement_id", "created_at"),
        Index("ix_capability_results_status", "status"),
    )

    requirement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("requirements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    customization_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_output: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    reviewed_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)

    requirement: Mapped[Requirement] = relationship(back_populates="capability_results")
    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="capability_results")
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    evidence_items: Mapped[list[CapabilityEvidence]] = relationship(back_populates="result")


class CapabilityEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "capability_evidence"
    __table_args__ = (
        UniqueConstraint(
            "capability_result_id",
            "qdrant_point_id",
            name="uq_capability_evidence_result_point",
        ),
        Index(
            "ix_capability_evidence_result_rank",
            "capability_result_id",
            "rank_position",
        ),
    )

    capability_result_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("capability_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qdrant_point_id: Mapped[str] = mapped_column(String(100), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    rerank_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)

    result: Mapped[CapabilityResult] = relationship(back_populates="evidence_items")
    document: Mapped[Document] = relationship(back_populates="evidence_items")
