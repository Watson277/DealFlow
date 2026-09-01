from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import WorkflowRunType, WorkflowStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.capability import CapabilityResult
    from app.models.proposal import Proposal
    from app.models.rfp import RFP


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint("attempt >= 0", name="attempt_nonnegative"),
        Index("ix_workflow_runs_rfp_status", "rfp_id", "status"),
        Index("ix_workflow_runs_status_created_at", "status", "created_at"),
    )

    rfp_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rfps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkflowRunType.FULL.value,
        server_default=WorkflowRunType.FULL.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkflowStatus.PENDING.value,
        server_default=WorkflowStatus.PENDING.value,
    )
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    input_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    output_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)

    rfp: Mapped[RFP] = relationship(back_populates="workflow_runs")
    capability_results: Mapped[list[CapabilityResult]] = relationship(back_populates="workflow_run")
    proposals: Mapped[list[Proposal]] = relationship(back_populates="workflow_run")
