"""add assistant_sessions table

Revision ID: add_assistant_sessions
Revises: <PUT_PREVIOUS_REVISION_ID_HERE>
Create Date: 2026-04-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "add_assistant_sessions"
down_revision = "e908a44528e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("client_session_id", sa.String(), nullable=False),
        sa.Column("current_state", sa.String(), nullable=False, server_default="NEW"),
        sa.Column("flow_mode", sa.String(), nullable=True),
        sa.Column("selected_specialty_id", sa.String(), nullable=True),
        sa.Column("selected_slot_id", sa.String(), nullable=True),
        sa.Column("selected_slot_label", sa.String(), nullable=True),
        sa.Column("selected_slot_start_utc", sa.String(), nullable=True),
        sa.Column("renewal_item_id", sa.String(), nullable=True),
        sa.Column("last_input_summary", sa.String(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "client_session_id",
            name="uq_assistant_session_tenant_client",
        ),
    )


def downgrade() -> None:
    op.drop_table("assistant_sessions")