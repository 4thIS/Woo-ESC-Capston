"""S4a §2.1 — 회원·메일 토큰. email 은 소문자 정규화된 웹메일 (PK). users 행은 verify 때 생긴다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

STATUSES = ("pending_approval", "active", "rejected", "disabled")
# #160 — admin = 최고 관리자(CLI), building_admin = 건물 관리자(웹 지정, user_buildings 범위), student = 일반 계정
ROLES = ("student", "admin", "building_admin")
ROLE_CHECK = "role IN ('student', 'admin', 'building_admin')"
HOLDS_STUDENT_NO = (
    "status IN ('pending_approval', 'active', 'disabled')"  # 거절 행은 학번을 잡지 않는다
)


class User(Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    role: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    student_no: Mapped[str | None] = mapped_column(String)
    pw_hash: Mapped[str] = mapped_column(String)  # "scrypt$n$r$p$<salt hex>$<hash hex>"
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")  # JWT tv
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    approved_at: Mapped[dt.datetime | None]
    approved_by: Mapped[str | None] = mapped_column(String)
    reject_reason: Mapped[str | None] = mapped_column(String)
    __table_args__ = (
        # 부분 유일 — 거절 행이 남의 학번을 영구 점유하지 않게. SQLite: NULL(관리자)은 유일성에서 제외
        Index(
            "uq_users_school_student_no",
            "school_id",
            "student_no",
            unique=True,
            sqlite_where=text(HOLDS_STUDENT_NO),
        ),
        CheckConstraint(ROLE_CHECK, name="ck_users_role"),
        CheckConstraint(
            "status IN ('pending_approval', 'active', 'rejected', 'disabled')",
            name="ck_users_status",
        ),
    )


class UserBuilding(Base):
    """건물 관리자가 맡은 건물 (#160, N:M). 사용자·건물을 지우면 함께 지워진다."""

    __tablename__ = "user_buildings"
    email: Mapped[str] = mapped_column(
        ForeignKey("users.email", ondelete="CASCADE"), primary_key=True
    )
    building_id: Mapped[int] = mapped_column(
        ForeignKey("buildings.id", ondelete="CASCADE"), primary_key=True
    )


class RoleChange(Base):
    """역할·건물 지정 기록 (#160) — 누가 언제 무엇으로 바꿨는지. 지우지 않는다."""

    __tablename__ = "role_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String)
    changed_by: Mapped[str] = mapped_column(String)
    changed_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    from_role: Mapped[str] = mapped_column(String)
    to_role: Mapped[str] = mapped_column(String)
    building_ids: Mapped[str] = mapped_column(String)  # 바뀐 뒤 건물 id JSON 배열


class EmailToken(Base):
    __tablename__ = "email_tokens"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)  # sha256 hex
    email: Mapped[str] = mapped_column(
        String
    )  # FK 아님 — verify 토큰은 users 행보다 먼저 (S4a §2.2)
    purpose: Mapped[str] = mapped_column(String)  # verify | reset
    created_at: Mapped[
        dt.datetime
    ]  # 재발송 간격·연장 상한의 기준 — expires_at 은 verify/open 이 늘린다
    expires_at: Mapped[dt.datetime]
    used_at: Mapped[dt.datetime | None]
    __table_args__ = (Index("ix_email_tokens_email", "email", "purpose"),)
