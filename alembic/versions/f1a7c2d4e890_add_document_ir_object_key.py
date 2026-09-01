"""add persisted DocumentIR object key

Revision ID: f1a7c2d4e890
Revises: e8f6c1a2b345
Create Date: 2026-09-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a7c2d4e890"
down_revision: str | None = "e8f6c1a2b345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("parsed_ir_object_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "parsed_ir_object_key")
