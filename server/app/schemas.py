"""요청/응답 모델 한 벌 (spec §4.3). 이후 필드는 additive."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, ClassVar, Literal

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


class StudentResvIn(BaseModel):
    date: dt.date
    s_h: int = Field(ge=0, le=23)
    s_m: int = Field(ge=0, le=59, multiple_of=5)
    e_h: int = Field(ge=0, le=23)
    e_m: int = Field(ge=0, le=59, multiple_of=5)
    subject: str = Field(min_length=1)

    @field_validator("subject")
    @classmethod
    def _subj(cls, v: str) -> str:
        return _bytes_max(v, P.SUBJ_MAX, "subject")

    @model_validator(mode="after")
    def _order(self):
        if (self.s_h, self.s_m) >= (self.e_h, self.e_m):
            raise ValueError("시작 < 끝")
        return self


class ResvOut(ResvIn, Out):
    id: int
    status: str = "approved"


class ResvMineOut(ResvOut):
    requested_at: dt.datetime | None
    decided_at: dt.datetime | None
    reject_reason: str | None
    checked_in_at: dt.datetime | None
    cancelled_at: dt.datetime | None
    room_id: int
    building: str
    room: int


class RequesterOut(BaseModel):
    email: str
    name: str
    student_no: str | None


class ResvAdminOut(ResvMineOut):
    requester: RequesterOut | None
    pushed_at: dt.datetime | None = None  # web A2 — NULL = 노드에 없음, 화면의 '예정' 배지


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
    # web A2 — 관리자 예약 표의 신청자·학번 열과 '예정' 배지. 관리자 전용 라우터에서만 쓴다
    requester: RequesterOut | None = None  # 관리자가 넣은 예약은 null
    pushed_at: dt.datetime | None = None


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
    # web A1 — 관리자 회원 목록의 거절 사유. 값은 status=rejected 행에만 있다: 재신청(verify)이 행을
    # 교체하고 /api/auth/me 는 active 만 통과하므로 학생 본인 응답에서는 구조적으로 null
    reject_reason: str | None = None


# ---- S4b §2.3 요약 ----


class ModemBriefOut(BaseModel):
    modem_id: str
    last_seen_at: dt.datetime | None
    buildings: list[str]


class WarningBucket(BaseModel):
    count: int
    items: list[
        Any
    ]  # 버킷마다 모양이 다르다 (NodeOut / FailedOut / PendingOut / UserOut / ModemBriefOut)


class SummaryTotals(BaseModel):
    buildings: int
    rooms: int
    nodes: int
    modems: int


class SummaryOut(BaseModel):
    as_of: dt.datetime
    totals: SummaryTotals
    warnings: dict[str, WarningBucket]


# ---- S10 §4.1 학생 조회 ----


class RoomStateOut(BaseModel):
    room_id: int
    building_id: int
    building: str
    bld: str
    room: int
    layout: int
    until: str | None


class FreeRoomOut(BaseModel):
    room_id: int
    building_id: int
    building: str
    bld: str
    room: int
    layout: int
    free_until: str | None


class ResvPublicOut(BaseModel):
    id: int
    date: dt.date
    s_h: int
    s_m: int
    e_h: int
    e_m: int
    mine: bool
    label: str


class FreeRange(BaseModel):
    from_: str = Field(alias="from")
    to: str
    model_config = ConfigDict(populate_by_name=True)


class BusySpan(FreeRange):
    label: str  # 남의 학생 예약·신청은 "예약됨" (room_state.public_label)
    type: int  # 1~6. 시험기간 안의 정규 슬롯은 2
    mine: bool
    # 내 예약만 — 격자가 '내 신청(대기)'과 '내 예약'을 가른다. 남의 것·슬롯은 None
    status: Literal["requested", "approved"] | None = None


class BusyDay(BaseModel):
    day: int  # 1=월 … 7=일 (SlotOut.day 와 같다)
    spans: list[BusySpan]


class WeekOut(BaseModel):
    room: RoomStateOut
    week_start: dt.date
    slots: list[SlotOut]
    reservations: list[ResvPublicOut]
    exams: list[ExamOut]
    busy: list[BusyDay] = []  # web A3 — 겹친 구간을 합친 요일별 사용 구간 (room_state.week_busy)


class JobRunOut(Out):
    id: int
    name: str
    ran_at: dt.datetime
    result: dict

    @field_validator("result", mode="before")
    @classmethod
    def _r(cls, v):
        return json.loads(v) if isinstance(v, str) else v


class AllocationOut(BaseModel):
    key: int
    label: str
    assigned_min: int
    unused_min: int
    total_min: int
    rate: float


class FreeSlotsOut(BaseModel):
    room_id: int
    room: int
    building: str
    free: list[FreeRange]


class ResvStatsRow(BaseModel):
    date: str
    requested: int
    approved: int
    rejected: int
    cancelled: int
    expired: int
    no_show: int
    checked_in: int


class ResvStatsOut(BaseModel):
    series: list[ResvStatsRow]
    totals: dict[str, int]
    no_show_rate: float
    checkin_rate: float


class LatencyBin(BaseModel):
    ge: int
    lt: int | None
    count: int


class LatencyOut(BaseModel):
    n: int
    bins: list[LatencyBin]
    p50: float | None
    p95: float | None
    max: float | None
    within_30s: float
    within_90s: float


class LatencySampleOut(BaseModel):
    outbox_id: int
    room_id: int
    bld: str
    room: int
    unit: int
    type: str
    created_at: dt.datetime
    finished_at: dt.datetime
    seconds: float
