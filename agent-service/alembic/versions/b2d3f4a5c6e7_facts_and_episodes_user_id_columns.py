"""facts and episodes user_id columns

Revision ID: b2d3f4a5c6e7
Revises: a1c2e3f4b5d6
Create Date: 2026-07-31 00:00:00.000000

Which end-user a piece of durable memory belongs to (mirrors
chat_sessions.user_id). Nullable for now: nothing writes facts/episodes yet
(no remember tool, consolidation not yet ported) — the column is added ahead
of that write path so it is required by construction once it lands, not
retrofitted. See docs/SECURITY.md for why this is not yet a verified identity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d3f4a5c6e7'
down_revision: Union[str, Sequence[str], None] = 'a1c2e3f4b5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "facts",
        sa.Column("user_id", sa.String(length=255), nullable=True),
        schema="agent",
    )
    op.create_index(
        "ix_facts_user_id", "facts", ["user_id"], schema="agent"
    )
    op.add_column(
        "episodes",
        sa.Column("user_id", sa.String(length=255), nullable=True),
        schema="agent",
    )
    op.create_index(
        "ix_episodes_user_id", "episodes", ["user_id"], schema="agent"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_episodes_user_id", table_name="episodes", schema="agent")
    op.drop_column("episodes", "user_id", schema="agent")
    op.drop_index("ix_facts_user_id", table_name="facts", schema="agent")
    op.drop_column("facts", "user_id", schema="agent")
