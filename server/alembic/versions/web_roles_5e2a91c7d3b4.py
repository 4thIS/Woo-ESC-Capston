"""web_roles — 관리자 권한 3단계 (#160, docs/specs/2026-11-17-roles-3tier-design.md §2)

users.role 에 building_admin, 건물 관리자 범위 user_buildings, 지정 기록 role_changes.

Revision ID: 5e2a91c7d3b4
Revises: 4c0a9f71e19d
Create Date: 2026-11-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5e2a91c7d3b4"
down_revision: str | Sequence[str] | None = "4c0a9f71e19d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HOLDS = sa.text("status IN ('pending_approval', 'active', 'disabled')")


def _recreate_users(role_check: str) -> None:
    # sqlite 는 CHECK 를 고치려면 표를 다시 만든다. 이름 붙인 CHECK(ck_users_status)는 반사돼 그대로 옮겨지고,
    # 옛 role CHECK 는 지우고 새 것을 table_args 로 넣는다. 부분 유일 인덱스(sqlite_where)는 batch 가 옮기지 못해
    # 직접 지웠다 다시 만든다
    op.drop_index("uq_users_school_student_no", table_name="users")
    with op.batch_alter_table(
        "users",
        recreate="always",
        table_args=(sa.CheckConstraint(role_check, name="ck_users_role"),),
        reflect_kwargs={"resolve_fks": False},
    ) as b:
        b.drop_constraint("ck_users_role", type_="check")
    op.create_index(
        "uq_users_school_student_no",
        "users",
        ["school_id", "student_no"],
        unique=True,
        sqlite_where=_HOLDS,
    )


def upgrade() -> None:
    _recreate_users("role IN ('student', 'admin', 'building_admin')")
    op.create_table(
        "user_buildings",
        sa.Column(
            "email",
            sa.String(),
            sa.ForeignKey("users.email", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "building_id",
            sa.Integer(),
            sa.ForeignKey("buildings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "role_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("from_role", sa.String(), nullable=False),
        sa.Column("to_role", sa.String(), nullable=False),
        sa.Column("building_ids", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("role_changes")
    op.drop_table("user_buildings")
    # 건물 관리자는 일반 계정으로 — 옛 CHECK 를 통과하게
    op.execute("UPDATE users SET role = 'student' WHERE role = 'building_admin'")
    _recreate_users("role IN ('student', 'admin')")
