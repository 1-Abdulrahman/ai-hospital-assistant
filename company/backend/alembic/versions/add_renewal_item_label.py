"""add renewal_item_label to assistant_sessions

Revision ID: add_renewal_item_label
Revises: add_renewal_patient_fields
Create Date: 2026-04-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "add_renewal_item_label"
down_revision = "add_renewal_patient_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_sessions",
        sa.Column("renewal_item_label", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assistant_sessions", "renewal_item_label")