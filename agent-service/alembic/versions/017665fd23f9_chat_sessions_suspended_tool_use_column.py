"""chat_sessions suspended_tool_use column

Revision ID: 017665fd23f9
Revises: c3e4f5a6b7d8
Create Date: 2026-08-03 23:26:54.260788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '017665fd23f9'
down_revision: Union[str, Sequence[str], None] = 'c3e4f5a6b7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Everything needed to resume one paused tool call (agent/tools/registry.py's
    # Tool.suspends): {tool_use_id, tool_name, turn_tail, system, payload,
    # iteration}. Null = nothing pending. Cleared atomically and only on a
    # genuine resolution — see SessionRepository.claim_suspended_tool_use.
    op.add_column(
        "chat_sessions",
        sa.Column(
            "suspended_tool_use",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema="agent",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_sessions", "suspended_tool_use", schema="agent")
