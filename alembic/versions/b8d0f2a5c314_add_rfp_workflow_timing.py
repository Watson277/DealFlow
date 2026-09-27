"""record upload-to-human-review workflow timing

Revision ID: b8d0f2a5c314
Revises: a7c9e1f4b203
Create Date: 2026-09-27 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "b8d0f2a5c314"
down_revision: str | None = "a7c9e1f4b203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rfps", sa.Column("workflow_started_at", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("rfps", sa.Column("review_ready_at", mysql.DATETIME(fsp=6), nullable=True))
    # Old records have no upload-arrival timestamp: retain NULL to label them estimated.
    # The first persisted proposal is the historical arrival at human review.
    op.execute(sa.text("""
        UPDATE rfps AS r
        JOIN (
            SELECT rfp_id, MIN(created_at) AS first_review_at
            FROM proposals GROUP BY rfp_id
        ) AS p ON p.rfp_id = r.id
        SET r.review_ready_at = p.first_review_at
        WHERE r.review_ready_at IS NULL
    """))


def downgrade() -> None:
    op.drop_column("rfps", "review_ready_at")
    op.drop_column("rfps", "workflow_started_at")
