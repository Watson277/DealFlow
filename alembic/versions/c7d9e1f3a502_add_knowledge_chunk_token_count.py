"""add knowledge chunk token count

Revision ID: c7d9e1f3a502
Revises: b2c4d6e8f901
Create Date: 2026-09-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d9e1f3a502"
down_revision: str | None = "b2c4d6e8f901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("token_count", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE knowledge_chunks "
        "SET token_count = GREATEST(1, CEILING(char_count / 4)) "
        "WHERE token_count IS NULL"
    )
    op.alter_column(
        "knowledge_chunks",
        "token_count",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_knowledge_chunks_token_count_positive"),
        "knowledge_chunks",
        "token_count > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_knowledge_chunks_token_count_positive"),
        "knowledge_chunks",
        type_="check",
    )
    op.drop_column("knowledge_chunks", "token_count")
