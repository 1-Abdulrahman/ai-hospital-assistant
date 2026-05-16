"""add clarification context to assistant sessions

Revision ID: add_clarification_context_to_assistant_sessions
Revises: add_continuity_context_to_assistant_sessions
Create Date: 2026-04-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "add_clarification_context_to_assistant_sessions"
down_revision = "add_continuity_context_to_assistant_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_sessions",
        sa.Column(
            "clarification_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "assistant_sessions",
        sa.Column("clarification_key", sa.String(), nullable=True),
    )
    op.add_column(
        "assistant_sessions",
        sa.Column("original_complaint_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_sessions",
        sa.Column("clarification_detail_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_sessions",
        sa.Column("merged_classification_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assistant_sessions", "merged_classification_text")
    op.drop_column("assistant_sessions", "clarification_detail_text")
    op.drop_column("assistant_sessions", "original_complaint_text")
    op.drop_column("assistant_sessions", "clarification_key")
    op.drop_column("assistant_sessions", "clarification_pending")