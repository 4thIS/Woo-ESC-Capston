"""분석 집계 (S10 §2.6). room_state 를 구간 병합으로 하루 단위 계산 — 분 루프 없음."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from itertools import pairwise

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.auth import scope
from app.domain import clock, reserve, room_state
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service.models import Outbox

OPEN_MIN, CLOSE_MIN = reserve.OPEN_MIN, reserve.CLOSE_MIN  # 운영 시간은 한 곳 (web A3 free)
MAX_DAYS = 90
DEFAULT_DAYS = 30
BINS = (0, 10, 20, 30, 45, 60, 90, 120)
WEEKDAY = "월화수목금토일"
LATENCY_TYPES = ("SLOT_SET", "RESV_SET")
RESV_KEYS = ("requested", "approved", "rejected", "cancelled", "expired", "no_show", "checked_in")


def parse_range(
    d_from: dt.date | None, d_to: dt.date | None, today: dt.date
) -> tuple[dt.date, dt.date]:
    d_to = d_to or today
    d_from = d_from or d_to - dt.timedelta(days=DEFAULT_DAYS - 1)
    if d_from > d_to or (d_to - d_from).days + 1 > MAX_DAYS:
        raise HTTPException(422, f"기간은 from ≤ to, {MAX_DAYS}일 이내")
    return d_from, d_to


def _days(d_from: dt.date, d_to: dt.date) -> list[dt.date]:
    return [d_from + dt.timedelta(days=i) for i in range((d_to - d_from).days + 1)]


def _school_rooms(s: Session, school_id: int, building_id: int | None):
    q = (
        select(Room, Building)
        .join(Building, Room.building_id == Building.id)
        .where(Building.school_id == school_id)
        .order_by(Building.bld, Room.room)
    )
    if building_id is not None:
        q = q.where(Building.id == building_id)
    return s.execute(q).all()


def _inputs_range(s: Session, room_ids: list[int], d_from: dt.date, d_to: dt.date):
    """방들의 슬롯(요일별)·승인 예약·시험기간을 쿼리 3개로 읽고, (room_id, date) → load_inputs
    와 같은 (slots, resvs, in_exam) 을 돌려주는 함수를 준다. 정렬도 load_inputs 와 같다.
    예약 Span 의 라벨은 r.subject 그대로(public_label 로 가리지 않음) — 레이아웃 계산(_segments)에만
    쓰고 응답에 싣지 않는다. 라벨을 밖으로 내보낼 일이 생기면 public_label 을 거칠 것."""
    slots: dict = defaultdict(list)
    for x in s.scalars(select(Slot).where(Slot.room_id.in_(room_ids)).order_by(Slot.s_h, Slot.s_m)):
        slots[x.room_id, x.day].append(
            room_state.Span(x.s_h * 60 + x.s_m, x.e_h * 60 + x.e_m, x.type, x.subject)
        )
    resvs: dict = defaultdict(list)
    for r in s.scalars(
        select(Reservation)
        .where(
            Reservation.room_id.in_(room_ids),
            Reservation.date.between(d_from, d_to),
            Reservation.status == "approved",
        )
        .order_by(Reservation.s_h, Reservation.s_m)
    ):
        resvs[r.room_id, r.date].append(
            room_state.Span(r.s_h * 60 + r.s_m, r.e_h * 60 + r.e_m, r.type, r.subject, id=r.id)
        )
    exams: dict = defaultdict(list)
    for e in s.scalars(
        select(ExamPeriod).where(
            ExamPeriod.room_id.in_(room_ids),
            ExamPeriod.date_start <= d_to,
            ExamPeriod.date_end >= d_from,
        )
    ):
        exams[e.room_id].append((e.date_start, e.date_end))

    def get(room_id: int, d: dt.date):
        in_exam = any(a <= d <= b for a, b in exams.get(room_id, ()))
        return slots.get((room_id, d.isoweekday()), []), resvs.get((room_id, d), []), in_exam

    return get


def _segments(
    slots: list[room_state.Span], resvs: list[room_state.Span], in_exam: bool
) -> list[tuple[int, int, int]]:
    """운영 시간 안의 배정 구간 (s, e, layout). room_state 를 변화점마다 호출해 이어 붙인다.
    배정 = layout ∈ {1,2,3,5,6,7} — 즉 FREE(4) 가 아닌 전부."""
    points = {OPEN_MIN, CLOSE_MIN, *(p for x in slots + resvs for p in (x.s, x.e))}
    for x in slots:
        if x.type == 1:  # 수업은 매시 50분·정각에 1↔2
            points.update(range(x.s - x.s % 60 + 50, x.e, 60))
            points.update(range(x.s - x.s % 60 + 60, x.e, 60))
    pts = sorted(p for p in points if OPEN_MIN <= p <= CLOSE_MIN)
    out: list[tuple[int, int, int]] = []
    for a, b in pairwise(pts):
        layout, _ = room_state.room_state(slots, resvs, in_exam, a)
        if layout == room_state.FREE:
            continue
        if out and out[-1][1] == a and out[-1][2] == layout:
            out[-1] = (out[-1][0], b, layout)
        else:
            out.append((a, b, layout))
    return out


def day_segments(s: Session, room_id: int, date: dt.date) -> list[tuple[int, int, int]]:
    return _segments(*room_state.load_inputs(s, room_id, date))


def allocation(
    s: Session,
    school_id: int,
    d_from: dt.date,
    d_to: dt.date,
    building_id: int | None,
    group: str,
) -> list[dict]:
    acc: dict = defaultdict(
        lambda: {"label": "", "assigned_min": 0, "unused_min": 0, "total_min": 0}
    )
    days = _days(d_from, d_to)
    rooms = _school_rooms(s, school_id, building_id)
    inputs = _inputs_range(s, [room.id for room, _ in rooms], d_from, d_to)
    for room, b in rooms:
        for d in days:
            if group == "room":
                key, label = room.id, f"{b.name} {room.room}"
            elif group == "building":
                key, label = b.id, b.name
            else:
                key, label = d.isoweekday(), WEEKDAY[d.isoweekday() - 1]
            a = acc[key]
            a["label"] = label
            a["total_min"] += CLOSE_MIN - OPEN_MIN
            for x0, x1, layout in _segments(*inputs(room.id, d)):
                a["assigned_min"] += x1 - x0
                if layout == 3:  # 휴강
                    a["unused_min"] += x1 - x0
    rows = [
        {"key": k, **v, "rate": round(v["assigned_min"] / v["total_min"], 4)}
        for k, v in acc.items()
    ]
    return sorted(rows, key=lambda r: (-r["rate"], r["key"]))


def free_slots(s: Session, school_id: int, date: dt.date, building_id: int | None) -> list[dict]:
    out = []
    rooms = _school_rooms(s, school_id, building_id)
    inputs = _inputs_range(s, [room.id for room, _ in rooms], date, date)
    for room, b in rooms:
        free, cur = [], OPEN_MIN
        for x0, x1, _ in _segments(*inputs(room.id, date)):
            if x0 > cur:
                free.append({"from": room_state.fmt_hhmm(cur), "to": room_state.fmt_hhmm(x0)})
            cur = max(cur, x1)
        if cur < CLOSE_MIN:
            free.append({"from": room_state.fmt_hhmm(cur), "to": room_state.fmt_hhmm(CLOSE_MIN)})
        out.append({"room_id": room.id, "room": room.room, "building": b.name, "free": free})
    return out


def reservation_stats(
    s: Session,
    school_id: int,
    d_from: dt.date,
    d_to: dt.date,
    group: str,
    now_local: dt.datetime,
) -> dict:
    """학생 신청(requested_by 있음)만. no_show = approved·종료 지남·미체크인."""

    def bucket(d: dt.date) -> str:
        return (d if group == "day" else clock.week_start(d)).isoformat()

    series: dict = defaultdict(lambda: dict.fromkeys(RESV_KEYS, 0))
    q = (
        select(Reservation)
        .join(Room, Room.id == Reservation.room_id)
        .join(Building, Building.id == Room.building_id)
        .where(
            Building.school_id == school_id,
            Reservation.requested_by.is_not(None),
            Reservation.date.between(d_from, d_to),
        )
    )
    ended = 0
    for r in s.scalars(q):
        row = series[bucket(r.date)]
        row["requested"] += 1
        if r.status in ("approved", "rejected", "cancelled", "expired"):
            row[r.status] += 1
        if r.status == "approved" and reserve.end_local(r) <= now_local:
            ended += 1
            row["no_show" if r.checked_in_at is None else "checked_in"] += 1
    labels = sorted({bucket(d) for d in _days(d_from, d_to)})
    out_series = [{"date": k, **series[k]} for k in labels]
    totals = {k: sum(x[k] for x in out_series) for k in RESV_KEYS}
    return {
        "series": out_series,
        "totals": totals,
        "no_show_rate": round(totals["no_show"] / ended, 4) if ended else 0.0,
        "checkin_rate": round(totals["checked_in"] / ended, 4) if ended else 0.0,
    }


def _latency_rows(
    s: Session, school_id: int, d_from: dt.date, d_to: dt.date, type_: str, limit=None
):
    lo = clock.to_utc(dt.datetime.combine(d_from, dt.time()))
    hi = clock.to_utc(dt.datetime.combine(d_to + dt.timedelta(days=1), dt.time()))
    types = LATENCY_TYPES if type_ == "all" else (type_,)
    # bld 재사용 뒤 남은 옛 학교(모뎀 소속) 행은 숨긴다 — admin.building_outbox 와 같은 규칙. NULL 통과.
    mids = scope.modem_ids(s, school_id)
    q = (
        select(Outbox, Room.id)
        .join(Building, and_(Building.bld == Outbox.bld, Building.school_id == school_id))
        .join(Room, and_(Room.building_id == Building.id, Room.room == Outbox.room))
        .where(
            Outbox.state == "acked",
            Outbox.type.in_(types),
            Outbox.created_at >= lo,
            Outbox.created_at < hi,
            Outbox.finished_at.is_not(None),
            Outbox.modem_id.is_(None) | Outbox.modem_id.in_(mids),
        )
        .order_by(Outbox.created_at.desc(), Outbox.id.desc())
        .limit(limit)
    )
    return s.execute(q).all()


def _secs(o: Outbox) -> float:
    return max(0.0, (o.finished_at - o.created_at).total_seconds())  # 시계 역행 → 0 (bin 합 = n)


def latency(s: Session, school_id: int, d_from: dt.date, d_to: dt.date, type_: str) -> dict:
    secs = sorted(_secs(o) for o, _ in _latency_rows(s, school_id, d_from, d_to, type_))
    n = len(secs)
    edges = [*BINS, None]
    bins = [
        {
            "ge": lo,
            "lt": hi,
            "count": sum(1 for x in secs if x >= lo and (hi is None or x < hi)),
        }
        for lo, hi in pairwise(edges)
    ]

    def pct(p: float) -> float | None:  # 하위 p 분위 = secs[int(p*(n-1))] (내림)
        return secs[int(p * (n - 1))] if n else None

    return {
        "n": n,
        "bins": bins,
        "p50": pct(0.5),
        "p95": pct(0.95),
        "max": secs[-1] if n else None,
        "within_30s": round(sum(1 for x in secs if x <= 30) / n, 4) if n else 0.0,
        "within_90s": round(sum(1 for x in secs if x <= 90) / n, 4) if n else 0.0,
    }


def latency_samples(
    s: Session, school_id: int, d_from: dt.date, d_to: dt.date, type_: str, limit: int
) -> list[dict]:
    rows = _latency_rows(s, school_id, d_from, d_to, type_, limit)
    return [
        {
            "outbox_id": o.id,
            "room_id": rid,
            "bld": o.bld,
            "room": o.room,
            "unit": o.unit,
            "type": o.type,
            "created_at": o.created_at,
            "finished_at": o.finished_at,
            "seconds": _secs(o),
        }
        for o, rid in rows
    ]
