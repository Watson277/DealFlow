"""add proposal content fields

Revision ID: c3f8b7d2e901
Revises: a054fdb05a3a
Create Date: 2026-08-30 20:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3f8b7d2e901"
down_revision: str | None = "a054fdb05a3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("markdown_object_key", sa.String(length=512), nullable=True),
    )
    op.add_column("proposals", sa.Column("content", sa.JSON(), nullable=True))
    op.execute("UPDATE proposals SET content = JSON_OBJECT() WHERE content IS NULL")
    op.alter_column("proposals", "content", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.drop_column("proposals", "content")
    op.drop_column("proposals", "markdown_object_key")
