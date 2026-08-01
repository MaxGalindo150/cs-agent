"""chat_sessions escalation columns

Revision ID: c3e4f5a6b7d8
Revises: b2d3f4a5c6e7
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e4f5a6b7d8'
down_revision: Union[str, Sequence[str], None] = 'b2d3f4a5c6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Presence, not a status enum: null = never escalated, non-null = when it
    # was. A session must never be silently re-escalated or its outcome lost
    # to a normal turn — see agent/runtime/session.py's fixed_response gate,
    # which short-circuits the LLM entirely once this is set.
    op.add_column(
        "chat_sessions",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        schema="agent",
    )
    op.add_column(
        "chat_sessions",
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        schema="agent",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_sessions", "escalation_reason", schema="agent")
    op.drop_column("chat_sessions", "escalated_at", schema="agent")
