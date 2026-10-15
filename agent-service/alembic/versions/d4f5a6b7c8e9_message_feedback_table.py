"""message_feedback table

Revision ID: d4f5a6b7c8e9
Revises: 017665fd23f9
Create Date: 2026-10-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4f5a6b7c8e9"
down_revision: Union[str, Sequence[str], None] = "017665fd23f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A user's thumbs up (1) / down (-1) on one assistant reply, with an
    # optional comment. Keyed by the message: one rating each, replaced when
    # the user rates again. Cascades with the message and the session, so
    # deleting a conversation leaves nothing behind.
    op.create_table(
        "message_feedback",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating IN (-1, 1)", name=op.f("ck_message_feedback_rating_valid")
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["agent.chat_messages.id"],
            name=op.f("fk_message_feedback_message_id_chat_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent.chat_sessions.id"],
            name=op.f("fk_message_feedback_session_id_chat_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_message_feedback")),
        schema="agent",
    )
    op.create_index(
        op.f("ix_message_feedback_session_id"),
        "message_feedback",
        ["session_id"],
        schema="agent",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_message_feedback_session_id"),
        table_name="message_feedback",
        schema="agent",
    )
    op.drop_table("message_feedback", schema="agent")
