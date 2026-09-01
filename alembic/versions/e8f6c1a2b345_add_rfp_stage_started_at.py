"""add RFP stage start timestamp

Revision ID: e8f6c1a2b345
Revises: d7e4a9b1c602
Create Date: 2026-08-31 00:00:00
"""

from collections.abc import Sequence

from sqlalchemy import Column
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "e8f6c1a2b345"
down_revision: str | None = "d7e4a9b1c602"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rfps",
        Column("stage_started_at", mysql.DATETIME(fsp=6), nullable=True),
    )
    op.execute("UPDATE rfps SET stage_started_at = COALESCE(processing_started_at, created_at)")


def downgrade() -> None:
    op.drop_column("rfps", "stage_started_at")
