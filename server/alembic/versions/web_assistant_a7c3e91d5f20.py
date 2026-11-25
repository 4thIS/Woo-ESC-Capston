"""web_assistant — 관리자 AI 비서 대화·턴 기록·미리보기·변경 기록

(docs/specs/2026-11-25-admin-ai-assistant-design.md §9). 새 표만 — 기존 표 불변.

Revision ID: a7c3e91d5f20
Revises: 5e2a91c7d3b4
Create Date: 2026-11-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c3e91d5f20"
down_revision: str | Sequence[str] | None = "5e2a91c7d3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_email",
            sa.String(),
            sa.ForeignKey("users.email", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_assistant_conv_updated", "assistant_conversations", ["updated_at"])
    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("form", sa.Text(), nullable=True),
        sa.Column("choice", sa.String(), nullable=True),
        sa.Column("reply_kind", sa.String(), nullable=False),
        sa.Column("reply_message", sa.Text(), nullable=False),
        sa.Column("model_rev", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_assistant_turns_created", "assistant_turns", ["created_at"])
    op.create_table(
        "assistant_previews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("draft", sa.Text(), nullable=False),
        sa.Column("ops", sa.Text(), nullable=False),
        sa.Column("room_ids", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("blockers", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_assistant_previews_expires", "assistant_previews", ["expires_at"])
    op.create_table(
        "assistant_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preview_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("building_ids", sa.Text(), nullable=False),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("ops", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("outbox_ids", sa.Text(), nullable=False),
        sa.Column("model_rev", sa.String(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_assistant_changes_school", "assistant_changes", ["school_id", "applied_at"])


def downgrade() -> None:
    op.drop_index("ix_assistant_changes_school", table_name="assistant_changes")
    op.drop_table("assistant_changes")
    op.drop_index("ix_assistant_previews_expires", table_name="assistant_previews")
    op.drop_table("assistant_previews")
    op.drop_index("ix_assistant_turns_created", table_name="assistant_turns")
    op.drop_table("assistant_turns")
    op.drop_index("ix_assistant_conv_updated", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
