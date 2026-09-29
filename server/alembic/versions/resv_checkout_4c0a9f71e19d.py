"""resv_checkout — 학생 조기 퇴실 시각 (docs/specs/2026-09-29-early-checkout-design.md §2)

Revision ID: 4c0a9f71e19d
Revises: b78771d56b6e
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c0a9f71e19d"
down_revision: str | Sequence[str] | None = "b78771d56b6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 이름 붙인 CHECK 를 table_args 로 — sqlite batch 재생성에서 익명 CHECK 가 사라지지 않게 (b78771d56b6e 와 같다)
    with op.batch_alter_table(
        "reservations",
        table_args=(sa.CheckConstraint("id BETWEEN 1 AND 65535", name="ck_resv_id"),),
    ) as b:
        b.add_column(sa.Column("checked_out_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reservations") as b:
        b.drop_column("checked_out_at")
