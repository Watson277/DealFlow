"""add incremental knowledge document and Child hash indexes

Revision ID: d4a8e2f6b901
Revises: c7d9e1f3a502
Create Date: 2026-09-03 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "d4a8e2f6b901"
down_revision: str | None = "c7d9e1f3a502"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"], unique=False)
    op.create_table(
        "knowledge_child_indexes",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("child_chunk_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=False),
        sa.Column("qdrant_point_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_order", sa.Integer(), nullable=False),
        sa.Column("child_order", sa.Integer(), nullable=False),
        sa.Column("structural_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_hash", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_knowledge_child_indexes_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_child_indexes"),
        sa.UniqueConstraint(
            "document_id",
            "child_chunk_id",
            name="uq_knowledge_child_indexes_document_chunk",
        ),
    )
    for index_name, column_name in (
        ("ix_knowledge_child_indexes_document", "document_id"),
        ("ix_knowledge_child_indexes_content_hash", "content_hash"),
        ("ix_knowledge_child_indexes_embedding_hash", "embedding_hash"),
        ("ix_knowledge_child_indexes_structural_hash", "structural_hash"),
    ):
        op.create_index(index_name, "knowledge_child_indexes", [column_name], unique=False)


def downgrade() -> None:
    op.drop_table("knowledge_child_indexes")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
