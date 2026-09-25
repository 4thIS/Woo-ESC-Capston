"""학생 API (S10 §4.1). require_student + 자기 학교 reservable 방. outbox 는 취소(T5)에서만."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.deps import StudentUser
from app.auth.models import User
from app.deps import _DB
from app.domain import clock, room_state
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot

router = APIRouter(prefix="/api/student", dependencies=[StudentUser])


def _rooms_q(user: User, building_id: int | None):
    q = (
        select(Room, Building)
        .join(Building, Room.building_id == Building.id)
        .where(Building.school_id == user.school_id, Room.reservable.is_(True))
        .order_by(Building.bld, Room.room)
    )
    return q if building_id is None else q.where(Building.id == building_id)


def _student_room(s: Session, user: User, room_id: int) -> tuple[Room, Building]:
    room = s.get(Room, room_id)
    b = s.get(Building, room.building_id) if room else None
    if room is None or b.school_id != user.school_id or not room.reservable:
        raise HTTPException(404, f"rooms {room_id} 없음")
    return room, b


def _state_out(s: Session, room: Room, b: Building, at: dt.datetime) -> dict:
    layout, until = room_state.state_of(s, room.id, at)
    return {
        "room_id": room.id,
        "building_id": b.id,
        "building": b.name,
        "bld": b.bld,
        "room": room.room,
        "layout": layout,
        "until": room_state.fmt_hhmm(until),
    }


@router.get("/rooms/free", response_model=list[S.FreeRoomOut])
def free_rooms(
    at: dt.datetime | None = None,
    building_id: int | None = None,
    user: User = StudentUser,
    s: Session = _DB,
):
    if (
        at is not None and at.tzinfo is not None
    ):  # 브라우저 toISOString() = "...Z" — 그대로 쓰면 9 시간 어긋난다
        at = at.astimezone(clock.SCHOOL_TZ).replace(tzinfo=None)
    at_local = at or clock.local_now()
    out = []
    for room, b in s.execute(_rooms_q(user, building_id)).all():
        st = _state_out(s, room, b, at_local)
        if st["layout"] == room_state.FREE:
            out.append({**st, "free_until": st.pop("until")})
    return out


@router.get("/rooms", response_model=list[S.RoomStateOut])
def rooms(building_id: int | None = None, user: User = StudentUser, s: Session = _DB):
    now = clock.local_now()
    return [_state_out(s, room, b, now) for room, b in s.execute(_rooms_q(user, building_id)).all()]


@router.get("/rooms/{id}/week", response_model=S.WeekOut)
def week(id: int, date: dt.date | None = None, user: User = StudentUser, s: Session = _DB):
    room, b = _student_room(s, user, id)
    start = clock.week_start(date or clock.local_today())
    end = start + dt.timedelta(days=6)
    resvs = []
    for r in s.scalars(
        select(Reservation)
        .where(
            Reservation.room_id == id,
            Reservation.status == "approved",
            Reservation.date.between(start, end),
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m)
    ):
        mine = r.requested_by is not None and r.requested_by == user.email
        resvs.append(
            {
                "id": r.id,
                "date": r.date,
                "s_h": r.s_h,
                "s_m": r.s_m,
                "e_h": r.e_h,
                "e_m": r.e_m,
                "mine": mine,
                "label": r.subject if (mine or r.requested_by is None) else "예약됨",
            }
        )
    return {
        "room": _state_out(s, room, b, clock.local_now()),
        "week_start": start,
        "slots": s.scalars(
            select(Slot).where(Slot.room_id == id).order_by(Slot.day, Slot.s_h, Slot.s_m)
        ).all(),
        "reservations": resvs,
        "exams": s.scalars(
            select(ExamPeriod)
            .where(
                ExamPeriod.room_id == id,
                ExamPeriod.date_start <= end,
                ExamPeriod.date_end >= start,
            )
            .order_by(ExamPeriod.date_start)
        ).all(),
    }
