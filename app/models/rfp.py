from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Computed, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Priority, RFPStatus
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.document import Document
    from app.models.proposal import Proposal
    from app.models.requirement import Requirement
    from app.models.user import User
    from app.models.workflow import WorkflowRun


class RFP(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "rfps"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "active_reference_number",
            name="uq_rfps_customer_active_reference_number",
        ),
        Index("ix_rfps_customer_status", "customer_id", "status"),
        Index("ix_rfps_status_created_at", "status", "created_at"),
        Index("ix_rfps_due_at", "due_at"),
    )

    customer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active_reference_number: Mapped[str | None] = mapped_column(
        String(100),
        Computed(
            "CASE WHEN deleted_at IS NULL THEN reference_number ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RFPStatus.UPLOADED.value,
        server_default=RFPStatus.UPLOADED.value,
    )
    current_stage: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="uploaded",
        server_default="uploaded",
    )
    priority: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=Priority.NORMAL.value,
        server_default=Priority.NORMAL.value,
    )
    source_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6),
        nullable=True,
    )
    stage_started_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    customer: Mapped[Customer] = relationship(back_populates="rfps")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    documents: Mapped[list[Document]] = relationship(back_populates="rfp")
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(back_populates="rfp")
    requirements: Mapped[list[Requirement]] = relationship(back_populates="rfp")
    proposals: Mapped[list[Proposal]] = relationship(back_populates="rfp")

    __mapper_args__ = {"version_id_col": row_version}
