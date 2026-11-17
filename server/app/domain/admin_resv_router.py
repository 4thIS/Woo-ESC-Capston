"""관리자 예약 승인·거절·취소 (S10 §4.2). 관리자 + 건물 범위(#160 — 학생 예약 승인은 그 건물의 건물 관리자와
최고 관리자만). 전역 작업(jobs)은 최고 관리자만."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import scope
from app.auth.deps import AdminUser, ManagerUser, MgrScope
from app.auth.scope import Scope
from app.deps import _DB
from app.domain import admin, analytics, clock, reserve
from app.domain.models import Building, JobRun, Reservation, Room
from app.domain.router import _ID_LOCK, _commit_notify

router = APIRouter(prefix="/api/admin", dependencies=[ManagerUser])


def _scoped_resv(s: Session, sc: Scope, id: int) -> Reservation:
    r = s.get(Reservation, id)
    b = s.get(Building, s.get(Room, r.room_id).building_id) if r is not None else None
    if b is None or b.school_id != sc.school_id or not sc.has(b.id):
        raise HTTPException(404, "예약 없음")
    return r


@router.get("/reservations", response_model=list[S.ResvAdminOut])
def list_reservations(
    status: str = "requested",
    building_id: int | None = None,
    date_from: clock.QDate | None = None,
    date_to: clock.QDate | None = None,
    limit: int = Query(500, ge=1, le=1000),
    sc: Scope = MgrScope,
    s: Session = _DB,
):
    q = (
        select(Reservation)
        .join(Room, Room.id == Reservation.room_id)
        .join(Building, Building.id == Room.building_id)
        .where(
            scope.building_clause(sc),
            Reservation.status.in_(reserve.parse_statuses(status)),
            # 시작 지난 신청은 승인 불가(409) — summary 의 pending_reservations 와 같은 규칙 (#49)
            (Reservation.status != "requested") | reserve.not_started(clock.local_now()),
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id)
        .limit(limit)
    )
    if building_id is not None:
        q = q.where(Building.id == building_id)
    if date_from is not None:
        q = q.where(Reservation.date >= date_from)
    if date_to is not None:
        q = q.where(Reservation.date <= date_to)
    return [admin.resv_admin_out(s, r) for r in s.scalars(q)]


@router.post("/reservations/{id}/approve", response_model=S.ResvAdminOut)
def approve(id: int, sc: Scope = MgrScope, s: Session = _DB):
    with (
        _ID_LOCK
    ):  # 겹침 재검사~커밋 — 동시에 들어온 학생 신청과 경합하지 않게 (학생 신청도 같은 락)
        r = _scoped_resv(s, sc, id)
        reserve.approve(s, r, sc.email, clock.local_now())
        out = admin.resv_admin_out(s, r)
        _commit_notify(
            s, reserve.addr(s, r)[2]
        )  # 같은 세션의 RESV_SET 을 커밋한 뒤 허브 알림 (S2c)
    return out


@router.post("/reservations/{id}/reject", response_model=S.ResvAdminOut)
def reject(id: int, body: S.RejectIn, sc: Scope = MgrScope, s: Session = _DB):
    with _ID_LOCK:
        r = _scoped_resv(s, sc, id)
        reserve.reject(s, r, sc.email, body.reason, clock.local_now())
        out = admin.resv_admin_out(s, r)
        s.commit()  # 락 안에서 — 응답 뒤 커밋이면 그 사이 승인과 엇갈린다
    return out


@router.post("/reservations/{id}/cancel", response_model=S.ResvAdminOut)
def cancel(id: int, sc: Scope = MgrScope, s: Session = _DB):
    with _ID_LOCK:
        r = _scoped_resv(s, sc, id)
        reserve.cancel(s, r, by_admin=True, now_local=clock.local_now())
        out = admin.resv_admin_out(s, r)
        _commit_notify(s, reserve.addr(s, r)[2])
    return out


@router.post("/jobs/daily", response_model=S.JobRunOut, dependencies=[AdminUser])
def run_daily_now(request: Request):
    """전 학교 대상 전역 작업(학교 스코프 없음) — 결과는 멱등(보낸 예약은 다시 안 보냄)이라 어느 관리자가 눌러도 안전.
    `_DB` 를 쓰지 않는다: run_daily 가 자기 세션들로 쓰고, 조회는 끝난 뒤 새 세션으로."""
    from app.domain import daily

    Session = request.app.state.Session
    jid = daily.run_daily(Session)
    with Session() as s:
        return S.JobRunOut.model_validate(s.get(JobRun, jid))


@router.get("/jobs", response_model=list[S.JobRunOut], dependencies=[AdminUser])
def jobs(name: str = "daily", limit: int = Query(30, ge=1, le=200), s: Session = _DB):
    return s.scalars(
        select(JobRun).where(JobRun.name == name).order_by(JobRun.id.desc()).limit(limit)
    ).all()


_FROM = Query(None, alias="from")
_LatencyType = Literal["SLOT_SET", "RESV_SET", "all"]


@router.get("/analytics/allocation", response_model=list[S.AllocationOut])
def analytics_allocation(
    from_: clock.QDate | None = _FROM,
    to: clock.QDate | None = None,
    building_id: int | None = None,
    group: Literal["room", "building", "weekday"] = "room",
    sc: Scope = MgrScope,
    s: Session = _DB,
):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.allocation(s, sc, d0, d1, building_id, group)


@router.get("/analytics/free-slots", response_model=list[S.FreeSlotsOut])
def analytics_free(
    date: clock.QDate | None = None,
    building_id: int | None = None,
    sc: Scope = MgrScope,
    s: Session = _DB,
):
    return analytics.free_slots(s, sc, date or clock.local_today(), building_id)


@router.get("/analytics/reservations", response_model=S.ResvStatsOut)
def analytics_resv(
    from_: clock.QDate | None = _FROM,
    to: clock.QDate | None = None,
    group: Literal["day", "week"] = "day",
    sc: Scope = MgrScope,
    s: Session = _DB,
):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.reservation_stats(s, sc, d0, d1, group, clock.local_now())


@router.get("/analytics/latency", response_model=S.LatencyOut)
def analytics_latency(
    from_: clock.QDate | None = _FROM,
    to: clock.QDate | None = None,
    type: _LatencyType = "all",
    sc: Scope = MgrScope,
    s: Session = _DB,
):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.latency(s, sc, d0, d1, type)


@router.get("/analytics/latency/samples", response_model=list[S.LatencySampleOut])
def analytics_samples(
    from_: clock.QDate | None = _FROM,
    to: clock.QDate | None = None,
    type: _LatencyType = "all",
    limit: int = Query(100, ge=1, le=1000),
    sc: Scope = MgrScope,
    s: Session = _DB,
):
    d0, d1 = analytics.parse_range(from_, to, clock.local_today())
    return analytics.latency_samples(s, sc, d0, d1, type, limit)
