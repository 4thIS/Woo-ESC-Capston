"""web_auth

Revision ID: 1739aef3234e
Revises: 6b47ab194f9a
Create Date: 2026-09-23 14:57:47.803564

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1739aef3234e"
down_revision: str | Sequence[str] | None = "6b47ab194f9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dup = conn.exec_driver_sql(
        "SELECT bld FROM buildings GROUP BY bld HAVING COUNT(DISTINCT school_id) > 1"
    ).fetchall()
    if dup:  # 공중 주소 (bld, room) 는 전역 — 학교 간에 겹치면 outbox·status 가 섞인다 (S4a §3.3)
        raise RuntimeError(
            f"bld 가 여러 학교에 겹침: {[r[0] for r in dup]} — 건물 bld 를 정리하고 다시 실행"
        )
    op.create_table(
        "users",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("student_no", sa.String(), nullable=True),
        sa.Column("pw_hash", sa.String(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("reject_reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("email"),
        sa.CheckConstraint("role IN ('student', 'admin')", name="ck_users_role"),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'active', 'rejected', 'disabled')",
            name="ck_users_status",
        ),
    )
    op.create_table(
        "email_tokens",
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(
        "uq_users_school_student_no",
        "users",
        ["school_id", "student_no"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending_approval', 'active', 'disabled')"),
    )
    op.create_index("ix_email_tokens_email", "email_tokens", ["email", "purpose"])
    with op.batch_alter_table("schools") as b:
        b.add_column(sa.Column("email_domain", sa.String(), nullable=True))
        b.create_unique_constraint("uq_schools_email_domain", ["email_domain"])
    # table_args 로 기존 이름 없는 CHECK(room BETWEEN..., units IN...)를 명시 — 재생성 시
    # "Unnamed CHECK constraint... omitted" 경고 없이 ck_rooms_room·ck_rooms_units 로 이름 붙는다
    with op.batch_alter_table(
        "rooms",
        table_args=(
            sa.CheckConstraint("room BETWEEN 1 AND 9999", name="ck_rooms_room"),
            sa.CheckConstraint("units IN (1, 2)", name="ck_rooms_units"),
        ),
    ) as b:
        b.add_column(sa.Column("reservable", sa.Boolean(), nullable=False, server_default="0"))
    with op.batch_alter_table("modems") as b:
        b.add_column(sa.Column("school_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_modems_school", "schools", ["school_id"], ["id"])
    op.execute(
        "UPDATE modems SET school_id = (SELECT b.school_id FROM buildings b"
        " WHERE b.modem_id = modems.modem_id)"
    )


def downgrade() -> None:
    with op.batch_alter_table("modems") as b:
        b.drop_constraint("fk_modems_school", type_="foreignkey")
        b.drop_column("school_id")
    with op.batch_alter_table("rooms") as b:
        b.drop_column("reservable")
    with op.batch_alter_table("schools") as b:
        b.drop_constraint("uq_schools_email_domain", type_="unique")
        b.drop_column("email_domain")
    op.drop_index("ix_email_tokens_email", table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_table("users")
