"""요청/응답 모델 한 벌 (spec §4.3). 이후 필드는 additive."""

from __future__ import annotations

import datetime as dt

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
    kinds: list[str] = ["schedule", "resv", "exam"]


class CmdIn(BaseModel):
    cmd: int = Field(ge=1, le=255)
    args_hex: str = ""


class Enqueued(BaseModel):
    outbox_ids: list[int]
