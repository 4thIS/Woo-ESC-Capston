"""학생 API (S10 §4.1). require_student + 자기 학교 reservable 방. outbox 는 취소에서만."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import ratelimit
from app.auth.deps import StudentUser
from app.auth.models import User
from app.deps import _DB
from app.domain import clock, reserve, room_state
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.domain.router import _ID_LOCK, _commit_notify, _free_id

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
    # 브라우저 toISOString() = "...Z" — 그대로 쓰면 9 시간 어긋난다
    if at is not None and at.tzinfo is not None:
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
        mine, label = room_state.public_label(r, user.email)
        resvs.append(
            {
                "id": r.id,
                "date": r.date,
                "s_h": r.s_h,
                "s_m": r.s_m,
                "e_h": r.e_h,
                "e_m": r.e_m,
                "mine": mine,
                "label": label,
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


def _mine_out(s: Session, r: Reservation) -> dict:
    room = s.get(Room, r.room_id)
    b = s.get(Building, room.building_id)
    return {
        **S.ResvOut.model_validate(r).model_dump(),
        "requested_at": r.requested_at,
        "decided_at": r.decided_at,
        "reject_reason": r.reject_reason,
        "checked_in_at": r.checked_in_at,
        "cancelled_at": r.cancelled_at,
        "room_id": room.id,
        "building": b.name,
        "room": room.room,
    }


def _my_resv(s: Session, user: User, id: int) -> Reservation:
    r = s.get(Reservation, id)
    if r is None or r.requested_by != user.email:
        raise HTTPException(404, "예약 없음")
    return r


DAILY_REQUESTS = 10  # 학생당 하루 신청 상한 — 신청·철회 반복으로 u16 id 를 소진하지 못하게


@router.post("/rooms/{id}/reservations", response_model=S.ResvMineOut, status_code=201)
def request_resv(id: int, body: S.StudentResvIn, user: User = StudentUser, s: Session = _DB):
    room, _ = _student_room(s, user, id)
    now = clock.local_now()
    # 검증~채번~커밋을 한 덩어리로 — 동시 두 신청이 둘 다 겹침·MAX_ACTIVE 검사를 통과하지 않게 (r2 🟡).
    # pysqlite 는 DML 전까지 트랜잭션을 열지 않아, 락 안의 SELECT 는 앞 요청의 커밋을 본다.
    with _ID_LOCK:
        reserve.validate_request(s, user, room, body, now)
        if not ratelimit.check(f"resv:{user.email}", limit=DAILY_REQUESTS, window_s=86400.0):
            raise HTTPException(429, f"신청은 하루 {DAILY_REQUESTS}회까지입니다")
        r = Reservation(
            id=_free_id(s, Reservation),
            room_id=id,
            date=body.date,
            s_h=body.s_h,
            s_m=body.s_m,
            e_h=body.e_h,
            e_m=body.e_m,
            type=reserve.STUDENT_TYPE,
            subject=body.subject,
            professor="",
            status="requested",
            requested_by=user.email,
            requested_at=clock.to_utc(now),
        )
        s.add(r)
        s.flush()
        out = _mine_out(s, r)
        s.commit()
    return out


@router.get("/me/reservations", response_model=list[S.ResvMineOut])
def my_reservations(status: str | None = None, user: User = StudentUser, s: Session = _DB):
    states = status.split(",") if status else ["requested", "approved"]
    q = (
        select(Reservation)
        .where(Reservation.requested_by == user.email, Reservation.status.in_(states))
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m)
    )
    return [_mine_out(s, r) for r in s.scalars(q)]


@router.post("/me/reservations/{id}/cancel", response_model=S.ResvMineOut)
def cancel_resv(id: int, user: User = StudentUser, s: Session = _DB):
    """requested → 철회(행 삭제), approved → 시작 전 취소(보낸 적 있으면 RESV_DEL). 커밋 뒤 허브 알림."""
    # 읽기~커밋 — 동시에 관리자가 승인하면 철회가 RESV_SET 뒤에 행을 지워 유령 예약이 남는다
    with _ID_LOCK:
        r = _my_resv(s, user, id)
        if r.status == "requested":
            out = _mine_out(s, r) | {"status": "cancelled"}
            reserve.withdraw(s, r)
            s.commit()
            return out
        mid = reserve.addr(s, r)[2]
        reserve.cancel(s, r, by_admin=False, now_local=clock.local_now())
        out = _mine_out(s, r)
        _commit_notify(s, mid)
    return out


@router.post("/me/reservations/{id}/checkin", response_model=S.ResvMineOut)
def checkin_resv(id: int, user: User = StudentUser, s: Session = _DB):
    with _ID_LOCK:  # 예약 쓰기 — 동시 취소와 엇갈려 cancelled 행에 checked_in_at 이 찍히지 않게
        r = _my_resv(s, user, id)
        reserve.checkin(s, r, clock.local_now())
        out = _mine_out(s, r)
        s.commit()
    return out
