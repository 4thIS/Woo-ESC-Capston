"""web_slot_source

Revision ID: 6b47ab194f9a
Revises: b3914933fd2a
Create Date: 2026-09-16 15:38:26.016722

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6b47ab194f9a"
down_revision: str | Sequence[str] | None = "b3914933fd2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행은 2(수동) — 포털 재업로드가 기존 데이터를 지우지 않도록 (S2b §2.2)
    op.add_column("slots", sa.Column("source", sa.Integer(), nullable=False, server_default="2"))


def downgrade() -> None:
    with op.batch_alter_table("slots") as b:
        b.drop_column("source")
