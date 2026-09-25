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
    # sqlite 의 익명 CHECK(원래 id BETWEEN...)는 reflection 이 못 읽어 재생성 경고를 내고 사라진다
    # (리뷰 🟡, 실측) — table_args 로 재생성될 새 테이블에 이름 붙여 명시해 경고 자체를 없앤다.
    with op.batch_alter_table(
        "reservations",
        table_args=(sa.CheckConstraint("id BETWEEN 1 AND 65535", name="ck_resv_id"),),
    ) as b:
        b.add_column(sa.Column("status", sa.String(), nullable=False, server_default="approved"))
        b.add_column(sa.Column("requested_by", sa.String(), nullable=True))
        b.add_column(sa.Column("requested_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("decided_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("decided_by", sa.String(), nullable=True))
        b.add_column(sa.Column("reject_reason", sa.String(), nullable=True))
        b.add_column(sa.Column("checked_in_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("cancelled_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("pushed_at", sa.DateTime(), nullable=True))
        b.create_check_constraint(
            "ck_resv_status",
            "status IN ('requested','approved','rejected','cancelled','expired')",
        )
        b.create_foreign_key("fk_resv_requester", "users", ["requested_by"], ["email"])
        b.create_index("ix_resv_room_date", ["room_id", "date"])
        b.create_index("ix_resv_requester", ["requested_by", "status"])
    # 기존 예약 중 창 안(KST 오늘~+7)이고 이미 RESV_SET 으로 노드에 나간 것만 pushed_at 을 채운다.
    # S2 는 등록 시점 창 안이면 바로 보냈지만, 창 밖(오늘+7 초과)으로 만들어진 예약은 한 번도 보낸 적
    # 없다 — 그런 행까지 pushed_at 을 채우면 첫 일일 승격이 그 행을 건너뛰어 노드에 영영 안 실린다.
    # RESV_DEL 이 아니라 RESV_SET 이력을 보는 이유: 지워진 적 없이 지금 창에 들어온 경우만 "이미 노드에
    # 있다"고 볼 수 있다. cancelled 상태 outbox 행(예: 방 재배정으로 취소된 발송)은 실제 전송이 아니므로
    # 제외한다.
    op.execute(
        "UPDATE reservations SET pushed_at = CURRENT_TIMESTAMP"
        " WHERE date BETWEEN date('now', '+9 hours') AND date('now', '+9 hours', '+7 days')"
        " AND EXISTS ("
        "   SELECT 1 FROM outbox"
        "   JOIN rooms ON rooms.id = reservations.room_id"
        "   JOIN buildings ON buildings.id = rooms.building_id"
        "   WHERE outbox.bld = buildings.bld AND outbox.room = rooms.room"
        "     AND outbox.type = 'RESV_SET' AND outbox.state != 'cancelled'"
        "     AND json_extract(outbox.payload, '$.resv_id') = reservations.id"
        " )"
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
