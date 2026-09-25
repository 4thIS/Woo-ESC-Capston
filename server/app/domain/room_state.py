"""강의실 상태 판정 — v2 §5.3 determineLayout·§5.4 nextChangeAt 의 서버판 (S10 §2.3).
입력은 분 단위 구간 목록이라 펌웨어와 같은 벡터로 검증한다."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import ExamPeriod, Reservation, Slot

TYPE_TO_LAYOUT = {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7}
FREE = 4
DAY_MIN = 24 * 60


@dataclass(frozen=True)
class Span:
    s: int  # 시작 분 (0..1439)
    e: int  # 끝 분 (배타)
    type: int
    label: str
    mine: bool = False
    id: int | None = None


def _inside(spans: list[Span], at: int) -> Span | None:
    return next((x for x in spans if x.s <= at < x.e), None)


def _next_start(spans: list[Span], at: int) -> int | None:
    starts = [x.s for x in spans if x.s > at]
    return min(starts) if starts else None


def room_state(
    slots: list[Span], resvs: list[Span], in_exam: bool, at_min: int
) -> tuple[int, int | None]:
    """(layout, until_min). until 은 다음 상태 변화 분; 자정 이후로 넘어가면 None."""
    nxt = min(
        (x for x in (_next_start(slots, at_min), _next_start(resvs, at_min)) if x is not None),
        default=None,
    )
    r = _inside(resvs, at_min)  # 예약(approved) > 시험기간 > 기본 (global.md 우선순위)
    if r is not None:
        layout, until = TYPE_TO_LAYOUT.get(r.type, FREE), r.e
    else:
        sl = _inside(slots, at_min)
        if sl is None:
            layout, until = FREE, nxt
        else:
            end = sl.e if nxt is None else min(sl.e, nxt)  # 슬롯 도중 예약이 시작될 수 있다
            if in_exam:
                layout, until = 5, end
            elif sl.type == 1:
                minute = at_min % 60
                if minute < 50:
                    layout, until = 1, min(end, at_min - minute + 50)
                else:
                    layout, until = 2, min(end, at_min - minute + 60)
            else:
                layout, until = TYPE_TO_LAYOUT.get(sl.type, FREE), end
    if until is not None and until >= DAY_MIN:  # "24:00" 은 없다 — 자정 이후는 다음 날 판정
        until = None
    return layout, until


def public_label(r, viewer_email: str | None) -> tuple[bool, str]:
    """남의 예약은 (False, "예약됨"). r 은 requested_by·subject 를 가진 예약 행(Reservation)."""
    mine = r.requested_by is not None and r.requested_by == viewer_email
    label = r.subject if (mine or r.requested_by is None) else "예약됨"
    return mine, label


def load_inputs(
    s: Session, room_id: int, date: dt.date, viewer_email: str | None = None
) -> tuple[list[Span], list[Span], bool]:
    """그 날짜의 정규 슬롯(요일)·승인 예약·시험기간 여부. 남의 예약은 label '예약됨'."""
    day = date.isoweekday()
    slots = [
        Span(x.s_h * 60 + x.s_m, x.e_h * 60 + x.e_m, x.type, x.subject)
        for x in s.scalars(
            select(Slot)
            .where(Slot.room_id == room_id, Slot.day == day)
            .order_by(Slot.s_h, Slot.s_m)
        )
    ]
    resvs = []
    for r in s.scalars(
        select(Reservation)
        .where(
            Reservation.room_id == room_id,
            Reservation.date == date,
            Reservation.status == "approved",
        )
        .order_by(Reservation.s_h, Reservation.s_m)
    ):
        mine, label = public_label(r, viewer_email)
        resvs.append(
            Span(
                r.s_h * 60 + r.s_m,
                r.e_h * 60 + r.e_m,
                r.type,
                label,
                mine,
                r.id,
            )
        )
    in_exam = (
        s.scalar(
            select(ExamPeriod.id)
            .where(
                ExamPeriod.room_id == room_id,
                ExamPeriod.date_start <= date,
                ExamPeriod.date_end >= date,
            )
            .limit(1)
        )
        is not None
    )
    return slots, resvs, in_exam


def state_of(s: Session, room_id: int, at_local: dt.datetime) -> tuple[int, int | None]:
    slots, resvs, in_exam = load_inputs(s, room_id, at_local.date())
    return room_state(slots, resvs, in_exam, at_local.hour * 60 + at_local.minute)


def fmt_hhmm(m: int | None) -> str | None:
    return None if m is None else f"{m // 60:02d}:{m % 60:02d}"
