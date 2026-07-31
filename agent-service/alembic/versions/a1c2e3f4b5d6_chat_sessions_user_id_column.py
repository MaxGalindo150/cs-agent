"""chat_sessions user_id column

Revision ID: a1c2e3f4b5d6
Revises: 864b6751885c
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c2e3f4b5d6'
down_revision: Union[str, Sequence[str], None] = '864b6751885c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Which end-user this conversation belongs to (service/core/identity.py).
    # Nullable: most sessions today have no identified user (no real auth yet),
    # and a session must be creatable before identity is known. NOT a
    # tenant/org column — one end-user, no isolation semantics (CLAUDE.md §9).
    op.add_column(
        "chat_sessions",
        sa.Column("user_id", sa.String(length=255), nullable=True),
        schema="agent",
    )
    op.create_index(
        "ix_chat_sessions_user_id",
        "chat_sessions",
        ["user_id"],
        schema="agent",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_chat_sessions_user_id", table_name="chat_sessions", schema="agent"
    )
    op.drop_column("chat_sessions", "user_id", schema="agent")
