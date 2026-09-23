"""spec §2.3 — lora_ 마이그레이션 계열. v2 §8.2를 로드맵 §4.5로 개정."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    modem_id: Mapped[str | None] = mapped_column(String)
    bld: Mapped[str] = mapped_column(String(1))
    room: Mapped[int]
    unit: Mapped[int]
    type: Mapped[str] = mapped_column(String)  # SLOT_SET … FILE CMD SET_ROOM
    payload: Mapped[str] = mapped_column(Text)  # JSON
    priority: Mapped[int] = mapped_column(default=5)
    new_ver: Mapped[int | None]
    state: Mapped[str] = mapped_column(String, default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    txn: Mapped[int | None]
    ack_status: Mapped[int | None]
    ack_detail: Mapped[int | None]
    rssi: Mapped[int | None]
    snr: Mapped[float | None]
    batt_mv: Mapped[int | None]
    layout: Mapped[int | None]
    fw: Mapped[int | None]
    sched_ver: Mapped[int | None]
    resv_ver: Mapped[int | None]
    exam_ver: Mapped[int | None]
    ident_ver: Mapped[int | None]
    last_error: Mapped[str | None]
    created_at: Mapped[datetime]
    dispatched_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    __table_args__ = (Index("ix_outbox_pick", "state", "modem_id", "priority", "id"),)


class Modem(Base):
    __tablename__ = "modems"
    modem_id: Mapped[str] = mapped_column(String, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String)  # sha256 hex
    agent_ver: Mapped[str | None]
    modem_fw: Mapped[str | None]
    last_seen_at: Mapped[datetime | None]
    connected: Mapped[bool] = mapped_column(default=False)
    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id")
    )  # 라우터 스코프 전용 — lora_service 코드는 읽지 않는다 (S4a §2.1)


class RoomVersion(Base):
    __tablename__ = "room_versions"
    bld: Mapped[str] = mapped_column(String(1), primary_key=True)
    room: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)  # schedule|resv|exam|ident
    ver: Mapped[int] = mapped_column(default=0)  # 1..255 롤링, 0 = 아직 없음


class TerminalStatus(Base):
    __tablename__ = "terminal_status"
    bld: Mapped[str] = mapped_column(String(1), primary_key=True)
    room: Mapped[int] = mapped_column(primary_key=True)
    unit: Mapped[int] = mapped_column(primary_key=True)
    modem_id: Mapped[str | None]
    mac: Mapped[str | None]
    fw: Mapped[int | None]
    batt_mv: Mapped[int | None]
    rssi: Mapped[int | None]
    snr: Mapped[float | None]
    sched_ver: Mapped[int | None]
    resv_ver: Mapped[int | None]
    exam_ver: Mapped[int | None]
    ident_ver: Mapped[int | None]
    layout: Mapped[int | None]
    clock_stale: Mapped[bool] = mapped_column(default=False)
    low_batt: Mapped[bool] = mapped_column(default=False)
    uptime_h: Mapped[int | None]
    last_seen_at: Mapped[datetime | None]
    last_ack_at: Mapped[datetime | None]
    last_status_at: Mapped[datetime | None]
    sync_state: Mapped[str] = mapped_column(
        String, default="unknown"
    )  # synced|pending|resync|unknown


class PendingDevice(Base):
    __tablename__ = "pending_devices"
    mac: Mapped[str] = mapped_column(String(12), primary_key=True)  # hex 12자
    modem_id: Mapped[str | None]
    fw: Mapped[int | None]
    batt_mv: Mapped[int | None]
    rssi: Mapped[int | None]
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]


class LoraLog(Base):
    __tablename__ = "lora_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime]
    modem_id: Mapped[str | None]
    dir: Mapped[str] = mapped_column(String(2))  # tx|rx (메인Pi 기준)
    t: Mapped[str] = mapped_column(String)  # 메시지 t
    body: Mapped[str] = mapped_column(Text)  # JSON
