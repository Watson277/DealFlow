"""add persisted knowledge parent chunks

Revision ID: b2c4d6e8f901
Revises: f1a7c2d4e890
Create Date: 2026-09-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "b2c4d6e8f901"
down_revision: str | None = "f1a7c2d4e890"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column(
            "chunk_level",
            sa.String(length=16),
            server_default="PARENT",
            nullable=False,
        ),
        sa.Column("chunk_order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("section_path", sa.JSON(), nullable=False),
        sa.Column("location", sa.JSON(), nullable=False),
        sa.Column("source_node_ids", sa.JSON(), nullable=False),
        sa.Column("block_types", sa.JSON(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_count > 0",
            name=op.f("ck_knowledge_chunks_char_count_positive"),
        ),
        sa.CheckConstraint(
            "chunk_level IN ('PARENT', 'CHILD')",
            name=op.f("ck_knowledge_chunks_chunk_level_valid"),
        ),
        sa.CheckConstraint(
            "chunk_order >= 0",
            name=op.f("ck_knowledge_chunks_chunk_order_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_knowledge_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_chunks"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_level",
            "chunk_order",
            name="uq_knowledge_chunks_document_level_order",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_content_hash",
        "knowledge_chunks",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_document_level",
        "knowledge_chunks",
        ["document_id", "chunk_level"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_document_level", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_content_hash", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
