"""allow anonymous proposal reviews

Revision ID: d7e4a9b1c602
Revises: c3f8b7d2e901
Create Date: 2026-08-31 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7e4a9b1c602"
down_revision: str | None = "c3f8b7d2e901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("fk_proposal_reviews_reviewer_id_users"),
        "proposal_reviews",
        type_="foreignkey",
    )
    op.drop_column("proposal_reviews", "reviewer_id")
    op.drop_constraint(
        op.f("fk_proposals_approved_by_id_users"),
        "proposals",
        type_="foreignkey",
    )
    op.drop_column("proposals", "approved_by_id")


def downgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("approved_by_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_proposals_approved_by_id_users"),
        "proposals",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("DELETE FROM proposal_reviews")
    op.add_column(
        "proposal_reviews",
        sa.Column("reviewer_id", sa.String(length=36), nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_proposal_reviews_reviewer_id_users"),
        "proposal_reviews",
        "users",
        ["reviewer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
