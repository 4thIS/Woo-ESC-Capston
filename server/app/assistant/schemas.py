"""AI 비서 HTTP 모양 (공통 부록 §4). 주간 데이터는 기존 SlotWithRoom·ResvWithRoom·ExamWithRoom 그대로."""

from __future__ import annotations

import datetime as dt
import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app import schemas as S


FORM_MAX = 4096  # form(JSON) 글자 수 상한 — 정상 form 은 수백 자


class TurnIn(BaseModel):
    conversation_id: str | None = Field(None, max_length=40)
    utterance: str = Field(min_length=1, max_length=300)
    form: dict | None = None
    choice: str | None = Field(None, max_length=80)
    # 브라우저가 두 번 시도해도 JSON 으로 못 읽은 모델 출력 원문 — 학습용 기록에 남기고 오류로 답한다
    raw_output: str | None = Field(None, max_length=2000)

    @field_validator("utterance")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("빈 말은 보낼 수 없습니다")
        return v

    @model_validator(mode="after")
    def _one(self):
        if self.form is not None and len(json.dumps(self.form, ensure_ascii=False)) > FORM_MAX:
            raise ValueError("form 이 너무 큽니다")
        if sum(x is not None for x in (self.form, self.choice, self.raw_output)) != 1:
            raise ValueError("form · choice · raw_output 중 정확히 하나")
        return self


class Choice(BaseModel):
    id: str
    label: str


class Mark(BaseModel):
    entity: Literal["slot", "resv", "exam"]
    key: str
    op: Literal["add", "remove", "change"]
    fields: list[str] = []


class WeekData(BaseModel):
    slots: list[S.SlotWithRoom]
    reservations: list[S.ResvWithRoom]
    exams: list[S.ExamWithRoom]


class PreviewWeek(BaseModel):
    week_start: dt.date | None
    before: WeekData
    after: WeekData
    changes: list[Mark]


class PreviewRoom(BaseModel):
    room_id: int
    building_id: int
    label: str
    added: int
    removed: int
    changed: int
    weeks: list[PreviewWeek]


class PreviewOut(BaseModel):
    preview_id: str
    expires_at: dt.datetime
    summary: list[str]
    blockers: list[str]
    warnings: list[str]
    notices: list[str]
    rooms: list[PreviewRoom]


class AnswerOut(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[str]]


class TurnOut(BaseModel):
    conversation_id: str
    kind: Literal["ask", "preview", "answer", "error"]
    message: str
    choices: list[Choice] = []
    next_prefix: str | None = None
    closed: bool = False
    preview: PreviewOut | None = None
    answer: AnswerOut | None = None


class ChangeOut(BaseModel):
    id: int
    applied_at: dt.datetime
    user_email: str
    utterance: str
    summary: list[str]
    outbox_ids: list[int]
