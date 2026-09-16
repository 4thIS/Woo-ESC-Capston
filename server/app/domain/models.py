"""spec §2.2 — web_ 마이그레이션 계열. 컬럼은 프로토콜 페이로드와 1:1."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    net_id: Mapped[int] = mapped_column(unique=True)  # 학교 단위 NET_ID (로드맵 §3)


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
    __table_args__ = (
        UniqueConstraint("building_id", "room"),
        CheckConstraint("room BETWEEN 1 AND 9999"),
        CheckConstraint("units IN (1, 2)"),
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
    __table_args__ = (CheckConstraint("id BETWEEN 1 AND 65535"),)


class ExamPeriod(Base):
    __tablename__ = "exam_periods"
    id: Mapped[int] = mapped_column(primary_key=True)  # = examId u16
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    date_start: Mapped[dt.date]
    date_end: Mapped[dt.date]
    __table_args__ = (CheckConstraint("id BETWEEN 1 AND 65535"),)
