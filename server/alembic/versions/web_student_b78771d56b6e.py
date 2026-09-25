"""web_student

Revision ID: b78771d56b6e
Revises: 1739aef3234e
Create Date: 2026-09-25 14:35:44.274897

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b78771d56b6e"
down_revision: str | Sequence[str] | None = "1739aef3234e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ran_at", sa.DateTime(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_runs_name", "job_runs", ["name", "ran_at"])
    with op.batch_alter_table("reservations") as b:
        b.add_column(sa.Column("status", sa.String(), nullable=False, server_default="approved"))
        b.add_column(sa.Column("requested_by", sa.String(), nullable=True))
        b.add_column(sa.Column("requested_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("decided_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("decided_by", sa.String(), nullable=True))
        b.add_column(sa.Column("reject_reason", sa.String(), nullable=True))
        b.add_column(sa.Column("checked_in_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("cancelled_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("pushed_at", sa.DateTime(), nullable=True))
        # add_column 만으로도 batch 모드가 테이블을 재생성하는데, sqlite 의 익명 CHECK 는 reflection 이
        # 못 읽어 재생성 뒤 사라진다 (리뷰 🟡, 실측) — 기존 id 범위 CHECK 를 이름 붙여 다시 만든다.
        b.create_check_constraint("ck_resv_id", "id BETWEEN 1 AND 65535")
        b.create_check_constraint(
            "ck_resv_status",
            "status IN ('requested','approved','rejected','cancelled','expired')",
        )
        b.create_foreign_key("fk_resv_requester", "users", ["requested_by"], ["email"])
        b.create_index("ix_resv_room_date", ["room_id", "date"])
        b.create_index("ix_resv_requester", ["requested_by", "status"])
    # 기존 예약 중 창 안(KST 오늘~+7)인 것은 S2 가 이미 노드로 보냈다 — pushed_at 을 NULL 로 두면
    # 배포 직후 삭제·취소에 RESV_DEL 이 안 나가 노드에 유령 예약이 남고, 첫 일일 작업이 오늘 한낮에
    # 창 안 예약을 전부 다시 보낸다 (자체 점검 🟡). 창 밖은 NULL 로 두어 승격 대상으로 남긴다.
    op.execute(
        "UPDATE reservations SET pushed_at = CURRENT_TIMESTAMP"
        " WHERE date BETWEEN date('now', '+9 hours') AND date('now', '+9 hours', '+7 days')"
    )


def downgrade() -> None:
    # ck_resv_id 는 이름 붙어 있어 reflection 이 재생성에 그대로 살려 낸다 — table_args 불필요.
    # ck_resv_status 는 status 컬럼을 참조하므로 그 컬럼을 지우기 전에 명시적으로 지운다.
    with op.batch_alter_table("reservations") as b:
        b.drop_constraint("fk_resv_requester", type_="foreignkey")
        b.drop_constraint("ck_resv_status", type_="check")
        b.drop_index("ix_resv_room_date")
        b.drop_index("ix_resv_requester")
        b.drop_column("status")
        b.drop_column("requested_by")
        b.drop_column("requested_at")
        b.drop_column("decided_at")
        b.drop_column("decided_by")
        b.drop_column("reject_reason")
        b.drop_column("checked_in_at")
        b.drop_column("cancelled_at")
        b.drop_column("pushed_at")
    op.drop_index("ix_job_runs_name", table_name="job_runs")
    op.drop_table("job_runs")
