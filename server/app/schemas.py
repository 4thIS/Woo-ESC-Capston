"""요청/응답 모델 한 벌 (spec §4.3). 이후 필드는 additive."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import ClassVar, Literal

from lora_proto import proto as P
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    reservable: bool = False


class RoomOut(RoomIn, Out):
    id: int


class _NoExplicitNull(BaseModel):
    """PATCH 공통: 보낸 필드에 명시적 null 은 422 (생략=부분 업데이트는 허용, 리뷰 finding 1).
    null 이 의미를 갖는 필드(예: BuildingPatch.modem_id)는 하위 클래스가 _nullable 에 넣는다."""

    _nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_explicit_null(self):
        bad = [
            f for f in self.model_fields_set if getattr(self, f) is None and f not in self._nullable
        ]
        if bad:
            raise ValueError(f"null 불가: {', '.join(bad)}")
        return self


class SchoolPatch(_NoExplicitNull):
    name: str | None = None  # net_id·email_domain 은 CLI 전용 (S4a §3.3)


class BuildingPatch(_NoExplicitNull):
    name: str | None = None
    bld: str | None = Field(None, min_length=1, max_length=1, pattern=r"^[A-Za-z]$")
    modem_id: str | None = None  # null = 모뎀 배정 해제 (리뷰: nullable 로 유지)

    _nullable: ClassVar[frozenset[str]] = frozenset({"modem_id"})


class RoomPatch(_NoExplicitNull):
    room: int | None = Field(None, ge=1, le=9999)
    units: int | None = Field(None, ge=1, le=2)
    reservable: bool | None = None


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
    id: int | None = Field(None, ge=1, le=65535)  # 없으면 서버 채번 (S4b §2.5)
    date: dt.date


class ResvOut(ResvIn, Out):
    id: int


class ExamIn(BaseModel):
    id: int | None = Field(None, ge=1, le=65535)
    date_start: dt.date
    date_end: dt.date


class ExamOut(ExamIn, Out):
    id: int


class SyncIn(BaseModel):
    kinds: list[Literal["schedule", "resv", "exam"]] = ["schedule", "resv", "exam"]


class CmdIn(BaseModel):
    cmd: int = Field(ge=1, le=255)
    args_hex: str = Field("", pattern=r"^([0-9a-fA-F]{2})*$")  # bytes.fromhex 가 받는 형태만


class Enqueued(BaseModel):
    outbox_ids: list[int]
    id: int | None = None  # 예약·시험 채번 결과 (S4b §2.5)


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
    school_id: int | None


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


class SlotWithRoom(SlotOut):
    room_id: int


class ResvWithRoom(ResvOut):
    room_id: int


class ExamWithRoom(ExamOut):
    room_id: int


class FailedOut(OutboxOut):
    """outbox + 방 조인 (S4b §2.4). 건물 단위 outbox·실패 목록·요약 미리보기가 같이 쓴다."""

    room_id: int
    building: str


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


class NodeOut(BaseModel):
    """기대 노드(rooms × units) × terminal_status (S4b §2.2). 보고 없는 노드는 상태 null + unseen."""

    room_id: int
    building_id: int
    building: str
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
    warnings: list[str]


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


# ---- S4a 인증 ----

# 단일 주소만 — @ 1개, 쉼표·공백·꺾쇠·따옴표 불가 (S4a §2.3, 리뷰 🔴1). 소문자 정규화 뒤 검사.
EMAIL_RE = re.compile(r"^[a-z0-9._+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$")


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.fullmatch(v):
            raise ValueError("이메일 형식이 아닙니다")
        return v


class TokenIn(BaseModel):
    # 길이는 VerifyIn·ResetIn 과 같다 — 짧은 무효 토큰도 422 가 아니라 400 링크 무효로 (test "nope")
    token: str = Field(min_length=1, max_length=128)


class VerifyIn(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=50)
    # ASCII 영숫자·하이픈만 — 공백·전각 숫자로 같은 학번을 두 번 만들어 유일성을 피하지 못하게 (자체 점검 🟡)
    student_no: str = Field(min_length=1, max_length=20, pattern=r"^[0-9A-Za-z-]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name", "student_no", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v  # strip 뒤 빈 문자열은 min_length 로 422

    @field_validator("student_no")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()  # ab123·AB123 이 같은 학번으로 잡히게 (PR #42 🟡)


class LoginIn(EmailIn):
    password: str = Field(max_length=128)


class LoginOut(BaseModel):
    token: str
    role: str
    school_id: int
    name: str


class ResetIn(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class UserOut(Out):
    email: str
    school_id: int
    role: str
    status: str
    name: str
    student_no: str | None
    created_at: dt.datetime
    approved_at: dt.datetime | None
