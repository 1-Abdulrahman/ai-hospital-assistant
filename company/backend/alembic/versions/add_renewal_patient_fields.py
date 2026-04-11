"""add renewal patient fields to assistant_sessions

Revision ID: add_renewal_patient_fields
Revises: add_assistant_sessions
Create Date: 2026-04-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "add_renewal_patient_fields"
down_revision = "add_assistant_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_sessions",
        sa.Column("renewal_patient_key_hash", sa.String(), nullable=True),
    )
    op.add_column(
        "assistant_sessions",
        sa.Column("renewal_patient_ref", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assistant_sessions", "renewal_patient_ref")
    op.drop_column("assistant_sessions", "renewal_patient_key_hash")