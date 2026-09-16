"""요청/응답 모델 한 벌 (spec §4.3). 이후 필드는 additive."""

from __future__ import annotations

import datetime as dt
import json
from typing import Literal

from lora_proto import proto as P
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _bytes_max(s: str, n: int, name: str) -> str:
    if len(s.encode("utf-8")) > n:
        raise ValueError(f"{name} {len(s.encode('utf-8'))} B > {n} B (UTF-8)")
    return s


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SchoolIn(BaseModel):
    name: str
    net_id: int = Field(ge=1, le=255)


class SchoolOut(SchoolIn, Out):
    id: int


class BuildingIn(BaseModel):
    school_id: int
    name: str
    bld: str = Field(min_length=1, max_length=1, pattern=r"^[A-Za-z]$")
    modem_id: str | None = None


class BuildingOut(BuildingIn, Out):
    id: int


class RoomIn(BaseModel):
    building_id: int
    room: int = Field(ge=1, le=9999)
    units: int = Field(default=1, ge=1, le=2)


class RoomOut(RoomIn, Out):
    id: int


class _Span(BaseModel):
    s_h: int = Field(ge=0, le=23)
    s_m: int = Field(ge=0, le=59)
    e_h: int = Field(ge=0, le=23)
    e_m: int = Field(ge=0, le=59)
    type: int = Field(ge=1, le=6)
    subject: str
    professor: str

    @field_validator("subject")
    @classmethod
    def _subj(cls, v: str) -> str:
        return _bytes_max(v, P.SUBJ_MAX, "subject")

    @field_validator("professor")
    @classmethod
    def _prof(cls, v: str) -> str:
        return _bytes_max(v, P.PROF_MAX, "professor")


class SlotIn(_Span):
    day: int = Field(ge=1, le=7)
    source: int = Field(2, ge=1, le=3)  # 1=포털 2=수동 3=긴급 (S2b §2.2)


class SlotOut(SlotIn, Out):
    id: int


class ResvIn(_Span):
    id: int = Field(ge=1, le=65535)
    date: dt.date


class ResvOut(ResvIn, Out):
    pass


class ExamIn(BaseModel):
    id: int = Field(ge=1, le=65535)
    date_start: dt.date
    date_end: dt.date


class ExamOut(ExamIn, Out):
    pass


class SyncIn(BaseModel):
    kinds: list[Literal["schedule", "resv", "exam"]] = ["schedule", "resv", "exam"]


class CmdIn(BaseModel):
    cmd: int = Field(ge=1, le=255)
    args_hex: str = ""


class Enqueued(BaseModel):
    outbox_ids: list[int]


class ImportSkipped(BaseModel):
    row: int
    reason: str


class ImportSummary(BaseModel):
    rooms: int
    added: int
    updated: int
    deleted: int
    skipped: list[ImportSkipped]
    outbox_ids: list[int]


class ImportRowError(BaseModel):
    row: int
    error: str


class ImportErrors(BaseModel):
    errors: list[ImportRowError]


class ModemIn(BaseModel):
    modem_id: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9-]+$")


class ModemOut(Out):
    modem_id: str
    agent_ver: str | None
    modem_fw: str | None
    last_seen_at: dt.datetime | None
    connected: bool


class TokenOut(BaseModel):
    modem_id: str
    token: str


class OutboxOut(Out):
    id: int
    modem_id: str | None
    bld: str
    room: int
    unit: int
    type: str
    payload: dict
    priority: int
    new_ver: int | None
    state: str
    attempts: int
    ack_status: int | None
    ack_detail: int | None
    rssi: int | None
    snr: float | None
    last_error: str | None
    created_at: dt.datetime
    dispatched_at: dt.datetime | None
    finished_at: dt.datetime | None

    @field_validator("payload", mode="before")
    @classmethod
    def _payload(cls, v):
        return json.loads(v) if isinstance(v, str) else v


class StatusOut(Out):
    bld: str
    room: int
    unit: int
    modem_id: str | None
    mac: str | None
    fw: int | None
    batt_mv: int | None
    rssi: int | None
    snr: float | None
    sched_ver: int | None
    resv_ver: int | None
    exam_ver: int | None
    ident_ver: int | None
    layout: int | None
    clock_stale: bool
    low_batt: bool
    uptime_h: int | None
    last_seen_at: dt.datetime | None
    last_ack_at: dt.datetime | None
    last_status_at: dt.datetime | None
    sync_state: str


class PendingOut(Out):
    mac: str
    modem_id: str | None
    fw: int | None
    batt_mv: int | None
    rssi: int | None
    first_seen_at: dt.datetime
    last_seen_at: dt.datetime


class ProvisionIn(BaseModel):
    bld: str = Field(min_length=1, max_length=1)
    room: int = Field(ge=1, le=9999)
    unit: int = Field(ge=1, le=2)
