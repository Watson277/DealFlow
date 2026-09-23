"""allow deleted RFP reference numbers to be reused

Revision ID: a7c9e1f4b203
Revises: f6a2c8d9e104
Create Date: 2026-09-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c9e1f4b203"
down_revision: str | None = "f6a2c8d9e104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_rfps_customer_reference_number",
        "rfps",
        type_="unique",
    )
    op.add_column(
        "rfps",
        sa.Column(
            "active_reference_number",
            sa.String(length=100),
            sa.Computed(
                "CASE WHEN deleted_at IS NULL THEN reference_number ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_rfps_customer_active_reference_number",
        "rfps",
        ["customer_id", "active_reference_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_rfps_customer_active_reference_number",
        "rfps",
        type_="unique",
    )
    op.drop_column("rfps", "active_reference_number")
    op.create_unique_constraint(
        "uq_rfps_customer_reference_number",
        "rfps",
        ["customer_id", "reference_number"],
    )
