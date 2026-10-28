"""S4a §2.1 — 회원·메일 토큰. email 은 소문자 정규화된 웹메일 (PK). users 행은 verify 때 생긴다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

STATUSES = ("pending_approval", "active", "rejected", "disabled")
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
        CheckConstraint("role IN ('student', 'admin')", name="ck_users_role"),
        CheckConstraint(
            "status IN ('pending_approval', 'active', 'rejected', 'disabled')",
            name="ck_users_status",
        ),
    )


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
