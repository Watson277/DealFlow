from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ProposalStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.rfp import RFP
    from app.models.workflow import WorkflowRun


class Proposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("rfp_id", "version", name="uq_proposals_rfp_version"),
        Index("ix_proposals_rfp_status", "rfp_id", "status"),
    )

    rfp_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rfps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProposalStatus.DRAFT.value,
        server_default=ProposalStatus.DRAFT.value,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    docx_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pdf_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)

    rfp: Mapped[RFP] = relationship(back_populates="proposals")
    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="proposals")
    reviews: Mapped[list[ProposalReview]] = relationship(back_populates="proposal")


class ProposalReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposal_reviews"
    __table_args__ = (Index("ix_proposal_reviews_proposal_created", "proposal_id", "created_at"),)

    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("proposals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    proposal: Mapped[Proposal] = relationship(back_populates="reviews")
