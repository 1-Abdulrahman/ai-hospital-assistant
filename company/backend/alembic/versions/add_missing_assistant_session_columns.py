"""add missing assistant_sessions columns

Revision ID: add_missing_assistant_session_columns
Revises: add_renewal_item_label
Create Date: 2026-04-12 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_missing_assistant_session_columns"
down_revision = "add_renewal_item_label"
branch_labels = None
depends_on = None


def _get_existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _get_existing_columns("assistant_sessions")

    if "selected_doctor_id" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("selected_doctor_id", sa.String(), nullable=True),
        )

    if "selected_date" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("selected_date", sa.String(), nullable=True),
        )

    if "renewal_item_label" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("renewal_item_label", sa.String(), nullable=True),
        )


def downgrade() -> None:
    existing = _get_existing_columns("assistant_sessions")

    if "renewal_item_label" in existing:
        op.drop_column("assistant_sessions", "renewal_item_label")

    if "selected_date" in existing:
        op.drop_column("assistant_sessions", "selected_date")

    if "selected_doctor_id" in existing:
        op.drop_column("assistant_sessions", "selected_doctor_id")