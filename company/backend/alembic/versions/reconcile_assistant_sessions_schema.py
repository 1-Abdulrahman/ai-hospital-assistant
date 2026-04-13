"""reconcile assistant_sessions schema with ORM

Revision ID: reconcile_assistant_sessions_schema
Revises: add_missing_assistant_session_columns
Create Date: 2026-04-12 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "reconcile_assistant_sessions_schema"
down_revision = "add_missing_assistant_session_columns"
branch_labels = None
depends_on = None


def _get_existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _get_existing_columns("assistant_sessions")

    if "selected_slot_label" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("selected_slot_label", sa.String(), nullable=True),
        )

    if "selected_slot_start_utc" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("selected_slot_start_utc", sa.String(), nullable=True),
        )

    if "last_input_summary" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("last_input_summary", sa.String(), nullable=True),
        )


def downgrade() -> None:
    existing = _get_existing_columns("assistant_sessions")

    if "last_input_summary" in existing:
        op.drop_column("assistant_sessions", "last_input_summary")

    if "selected_slot_start_utc" in existing:
        op.drop_column("assistant_sessions", "selected_slot_start_utc")

    if "selected_slot_label" in existing:
        op.drop_column("assistant_sessions", "selected_slot_label")