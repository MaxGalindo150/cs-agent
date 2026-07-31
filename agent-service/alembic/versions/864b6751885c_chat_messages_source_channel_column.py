"""chat_messages source channel column

Revision ID: 864b6751885c
Revises: 81eb545e5152
Create Date: 2026-07-22 19:10:01.810678

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '864b6751885c'
down_revision: Union[str, Sequence[str], None] = '81eb545e5152'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The input channel a message arrived through (Waku's chat_log.source).
    # Nullable and open-ended (no CHECK) — channels are added, not enumerated.
    op.add_column(
        "chat_messages",
        sa.Column("source", sa.String(length=32), nullable=True),
        schema="agent",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_messages", "source", schema="agent")
