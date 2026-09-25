"""관리자 예약 승인·거절·취소 (S10 §4.2). 전부 관리자 + 학교 스코프."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.deps import AdminUser
from app.auth.models import User
from app.deps import _DB
from app.domain import admin, clock, reserve
from app.domain.models import Building, Reservation, Room
from app.domain.router import _ID_LOCK, _commit_notify

router = APIRouter(prefix="/api/admin", dependencies=[AdminUser])


def _scoped_resv(s: Session, user: User, id: int) -> Reservation:
    r = s.get(Reservation, id)
    if r is None or s.get(Building, s.get(Room, r.room_id).building_id).school_id != user.school_id:
        raise HTTPException(404, "예약 없음")
    return r


@router.get("/reservations", response_model=list[S.ResvAdminOut])
def list_reservations(
    status: str = "requested",
    building_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    user: User = AdminUser,
    s: Session = _DB,
):
    q = (
        select(Reservation)
        .join(Room, Room.id == Reservation.room_id)
        .join(Building, Building.id == Room.building_id)
        .where(Building.school_id == user.school_id, Reservation.status.in_(status.split(",")))
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id)
    )
    if building_id is not None:
        q = q.where(Building.id == building_id)
    if date_from is not None:
        q = q.where(Reservation.date >= date_from)
    if date_to is not None:
        q = q.where(Reservation.date <= date_to)
    return [admin.resv_admin_out(s, r) for r in s.scalars(q)]


@router.post("/reservations/{id}/approve", response_model=S.ResvAdminOut)
def approve(id: int, user: User = AdminUser, s: Session = _DB):
    with (
        _ID_LOCK
    ):  # 겹침 재검사~커밋 — 동시에 들어온 학생 신청과 경합하지 않게 (학생 신청도 같은 락)
        r = _scoped_resv(s, user, id)
        reserve.approve(s, r, user.email, clock.local_now())
        out = admin.resv_admin_out(s, r)
        _commit_notify(
            s, reserve.addr(s, r)[2]
        )  # 같은 세션의 RESV_SET 을 커밋한 뒤 허브 알림 (S2c)
    return out


@router.post("/reservations/{id}/reject", response_model=S.ResvAdminOut)
def reject(id: int, body: S.RejectIn, user: User = AdminUser, s: Session = _DB):
    with _ID_LOCK:
        r = _scoped_resv(s, user, id)
        reserve.reject(s, r, user.email, body.reason, clock.local_now())
        out = admin.resv_admin_out(s, r)
        s.commit()  # 락 안에서 — 응답 뒤 커밋이면 그 사이 승인과 엇갈린다
    return out


@router.post("/reservations/{id}/cancel", response_model=S.ResvAdminOut)
def cancel(id: int, user: User = AdminUser, s: Session = _DB):
    with _ID_LOCK:
        r = _scoped_resv(s, user, id)
        reserve.cancel(s, r, by_admin=True, now_local=clock.local_now())
        out = admin.resv_admin_out(s, r)
        _commit_notify(s, reserve.addr(s, r)[2])
    return out
