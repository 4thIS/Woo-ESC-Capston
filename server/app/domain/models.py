"""spec §2.2 — web_ 마이그레이션 계열. 컬럼은 프로토콜 페이로드와 1:1."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    net_id: Mapped[int] = mapped_column(unique=True)  # 학교 단위 NET_ID (로드맵 §3)
    email_domain: Mapped[str | None] = mapped_column(
        String, unique=True
    )  # 학생 가입 도메인 — CLI 로만 (S4a §3.3)


class Building(Base):
    __tablename__ = "buildings"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    name: Mapped[str] = mapped_column(String)
    bld: Mapped[str] = mapped_column(String(1))  # 헤더 BLD 바이트 (ASCII)
    modem_id: Mapped[str | None] = mapped_column(ForeignKey("modems.modem_id"))
    __table_args__ = (UniqueConstraint("school_id", "bld"),)


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"))
    room: Mapped[int]
    units: Mapped[int] = mapped_column(default=1)
    reservable: Mapped[bool] = mapped_column(
        default=False, server_default="0"
    )  # 학생 예약 신청 가능 (S10)
    __table_args__ = (
        UniqueConstraint("building_id", "room"),
        CheckConstraint("room BETWEEN 1 AND 9999", name="ck_rooms_room"),
        CheckConstraint("units IN (1, 2)", name="ck_rooms_units"),
    )


class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    day: Mapped[int]
    s_h: Mapped[int]
    s_m: Mapped[int]
    e_h: Mapped[int]
    e_m: Mapped[int]
    type: Mapped[int]
    subject: Mapped[str] = mapped_column(String)
    professor: Mapped[str] = mapped_column(String)
    # 1=포털 2=수동 3=긴급 (S2b §2.2)
    source: Mapped[int] = mapped_column(default=2, server_default="2")
    __table_args__ = (UniqueConstraint("room_id", "day", "s_h", "s_m"),)  # 노드 멱등키와 동일


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(primary_key=True)  # = resvId u16
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    date: Mapped[dt.date]
    s_h: Mapped[int]
    s_m: Mapped[int]
    e_h: Mapped[int]
    e_m: Mapped[int]
    type: Mapped[int]
    subject: Mapped[str] = mapped_column(String)
    professor: Mapped[str] = mapped_column(String)
    # ---- S10 §2.1 학생 신청 ----
    status: Mapped[str] = mapped_column(String, default="approved", server_default="approved")
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.email"))
    requested_at: Mapped[dt.datetime | None]
    decided_at: Mapped[dt.datetime | None]
    decided_by: Mapped[str | None] = mapped_column(String)
    reject_reason: Mapped[str | None] = mapped_column(String)
    checked_in_at: Mapped[dt.datetime | None]
    cancelled_at: Mapped[dt.datetime | None]
    # 마지막으로 RESV_SET 을 enqueue 한 시각. NULL = 노드에 없다(안 보냈거나 RESV_DEL 로 지움).
    # 승격·RESV_DEL 판단을 outbox 이력 대신 이 칸으로 — id 재사용·놓친 날에 안전 (S10 §2.5, r3)
    pushed_at: Mapped[dt.datetime | None]
    __table_args__ = (
        CheckConstraint("id BETWEEN 1 AND 65535", name="ck_resv_id"),
        CheckConstraint(
            "status IN ('requested','approved','rejected','cancelled','expired')",
            name="ck_resv_status",
        ),
        Index("ix_resv_room_date", "room_id", "date"),
        Index("ix_resv_requester", "requested_by", "status"),
    )


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    ran_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    result: Mapped[str] = mapped_column(Text)  # JSON
    __table_args__ = (Index("ix_job_runs_name", "name", "ran_at"),)


class ExamPeriod(Base):
    __tablename__ = "exam_periods"
    id: Mapped[int] = mapped_column(primary_key=True)  # = examId u16
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    date_start: Mapped[dt.date]
    date_end: Mapped[dt.date]
    __table_args__ = (CheckConstraint("id BETWEEN 1 AND 65535"),)
