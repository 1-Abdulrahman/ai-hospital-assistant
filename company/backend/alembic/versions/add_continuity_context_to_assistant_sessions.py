"""add continuity context to assistant_sessions

Revision ID: add_continuity_context_to_assistant_sessions
Revises: reconcile_assistant_sessions_schema
Create Date: 2026-04-12 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "add_continuity_context_to_assistant_sessions"
down_revision = "reconcile_assistant_sessions_schema"
branch_labels = None
depends_on = None


def _get_existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _get_existing_columns("assistant_sessions")

    if "continuity_checked" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column(
                "continuity_checked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    if "continuity_patient_ref" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("continuity_patient_ref", sa.String(), nullable=True),
        )

    if "continuity_preferred_practitioner_ref" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("continuity_preferred_practitioner_ref", sa.String(), nullable=True),
        )

    if "continuity_preferred_practitioner_display" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column("continuity_preferred_practitioner_display", sa.String(), nullable=True),
        )

    if "continuity_is_returning" not in existing:
        op.add_column(
            "assistant_sessions",
            sa.Column(
                "continuity_is_returning",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    existing = _get_existing_columns("assistant_sessions")

    if "continuity_is_returning" in existing:
        op.drop_column("assistant_sessions", "continuity_is_returning")

    if "continuity_preferred_practitioner_display" in existing:
        op.drop_column("assistant_sessions", "continuity_preferred_practitioner_display")

    if "continuity_preferred_practitioner_ref" in existing:
        op.drop_column("assistant_sessions", "continuity_preferred_practitioner_ref")

    if "continuity_patient_ref" in existing:
        op.drop_column("assistant_sessions", "continuity_patient_ref")

    if "continuity_checked" in existing:
        op.drop_column("assistant_sessions", "continuity_checked")