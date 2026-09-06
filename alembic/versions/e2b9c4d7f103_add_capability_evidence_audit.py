"""add capability citation audit and immutable evidence snapshots

Revision ID: e2b9c4d7f103
Revises: d4a8e2f6b901
Create Date: 2026-09-06 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2b9c4d7f103"
down_revision: str | None = "d4a8e2f6b901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("capability_results", sa.Column("citation_audit", sa.JSON(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE capability_results "
            "SET citation_audit = JSON_OBJECT('validation_status', 'LEGACY_UNVERIFIED') "
            "WHERE citation_audit IS NULL"
        )
    )
    op.alter_column(
        "capability_results",
        "citation_audit",
        existing_type=sa.JSON(),
        nullable=False,
    )

    snapshot_columns = (
        sa.Column("document_title", sa.String(length=255), nullable=True),
        sa.Column("document_version", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("parent_id", sa.String(length=100), nullable=True),
        sa.Column("child_chunk_id", sa.String(length=100), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("matched_child_text", sa.Text(), nullable=True),
        sa.Column("section_path", sa.JSON(), nullable=True),
        sa.Column("block_types", sa.JSON(), nullable=True),
        sa.Column("source_block_ids", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_location", sa.JSON(), nullable=True),
        sa.Column("retrieval_mode", sa.String(length=16), nullable=True),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("selection_order", sa.Integer(), nullable=True),
    )
    for column in snapshot_columns:
        op.add_column("capability_evidence", column)

    op.create_unique_constraint(
        "uq_capability_evidence_result_selection_order",
        "capability_evidence",
        ["capability_result_id", "selection_order"],
    )
    op.create_check_constraint(
        "ck_capability_evidence_selection_order_positive",
        "capability_evidence",
        "selection_order IS NULL OR selection_order > 0",
    )
    op.create_check_constraint(
        "ck_capability_evidence_selection_state_consistent",
        "capability_evidence",
        "(is_selected = 0 AND selection_order IS NULL) OR "
        "(is_selected = 1 AND selection_order IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_capability_evidence_selection_state_consistent",
        "capability_evidence",
        type_="check",
    )
    op.drop_constraint(
        "ck_capability_evidence_selection_order_positive",
        "capability_evidence",
        type_="check",
    )
    op.drop_constraint(
        "uq_capability_evidence_result_selection_order",
        "capability_evidence",
        type_="unique",
    )
    for column_name in (
        "selection_order",
        "is_selected",
        "retrieval_mode",
        "source_location",
        "source_type",
        "source_block_ids",
        "block_types",
        "section_path",
        "matched_child_text",
        "page_end",
        "child_chunk_id",
        "parent_id",
        "category",
        "document_version",
        "document_title",
    ):
        op.drop_column("capability_evidence", column_name)
    op.drop_column("capability_results", "citation_audit")
