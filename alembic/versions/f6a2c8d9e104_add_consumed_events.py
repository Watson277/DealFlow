"""add consumed events for Kafka consumer deduplication

Revision ID: f6a2c8d9e104
Revises: e2b9c4d7f103
Create Date: 2026-09-07 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "f6a2c8d9e104"
down_revision: str | None = "e2b9c4d7f103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consumed_events",
        sa.Column("consumer_group", sa.String(length=100), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("partition", sa.Integer(), nullable=False),
        sa.Column("offset", sa.BigInteger(), nullable=False),
        sa.Column(
            "consumed_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_consumed_events"),
        sa.UniqueConstraint(
            "consumer_group",
            "event_id",
            name="uq_consumed_events_group_event",
        ),
        sa.UniqueConstraint(
            "consumer_group",
            "topic",
            "partition",
            "offset",
            name="uq_consumed_events_group_topic_partition_offset",
        ),
    )
    op.create_index(
        "ix_consumed_events_consumed_at",
        "consumed_events",
        ["consumed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_consumed_events_consumed_at", table_name="consumed_events")
    op.drop_table("consumed_events")
