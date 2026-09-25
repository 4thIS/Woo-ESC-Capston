"""lora_service 가 주입받는 두 콜백의 domain 구현 (spec §3 의존 방향)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from lora_proto import codec as C
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain import clock
from app.domain.models import Building, ExamPeriod, Reservation, Room, School, Slot
from app.lora_service.api import RoomInfo

RESV_HORIZON_DAYS = 7  # v2 §12: 예약은 오늘~7일 이내만 노드로
NODE_RESV_MAX = 24  # 노드 Resv resv[24] (v2 §5.1). T3 의 reserve.NODE_RESV_MAX 가 이 값을 import


def _room_q(bld: str, room: int):
    return (
        select(Room, Building, School)
        .join(Building, Room.building_id == Building.id)
        .join(School, Building.school_id == School.id)
        .where(Building.bld == bld, Room.room == room)
    )


class DomainTopology:
    def __init__(self, session_factory: sessionmaker):
        self._Session = session_factory

    def room(self, bld: str, room: int) -> RoomInfo | None:
        with self._Session() as s:
            hits = s.execute(_room_q(bld, room)).all()
        if not hits:
            return None
        if len(hits) > 1:
            raise LookupError(f"bld {bld!r} 가 여러 학교에 있음 — 운영 규칙 위반")
        r, b, sch = hits[0]
        return RoomInfo(b.modem_id, r.units, sch.net_id)

    def nodes(self, modem_id: str) -> list[tuple[str, int, int]]:
        with self._Session() as s:
            rows = s.execute(
                select(Building.bld, Room.room, Room.units)
                .join(Room, Room.building_id == Building.id)
                .where(Building.modem_id == modem_id)
            ).all()
        return [(b, r, u) for b, r, units in rows for u in range(1, units + 1)]

    def net_id(self, modem_id: str) -> int | None:
        with self._Session() as s:
            return s.scalar(
                select(School.net_id)
                .join(Building, Building.school_id == School.id)
                .where(Building.modem_id == modem_id)
            )


def record_provider(
    session_factory: sessionmaker, today: Callable[[], dt.date] = clock.local_today
) -> Callable[[str, int, str], list]:
    def _room_id(s: Session, bld: str, room: int) -> int | None:
        hit = s.execute(_room_q(bld, room)).first()
        return None if hit is None else hit[0].id

    def fn(bld: str, room: int, kind: str) -> list:
        with session_factory() as s:
            rid = _room_id(s, bld, room)
            if rid is None:
                return []
            if kind == "schedule":
                return [
                    C.SlotSet(0, x.day, x.s_h, x.s_m, x.e_h, x.e_m, x.type, x.subject, x.professor)
                    for x in s.scalars(
                        select(Slot)
                        .where(Slot.room_id == rid)
                        .order_by(Slot.day, Slot.s_h, Slot.s_m)
                    )
                ]
            if kind == "resv":
                lo, hi = today(), today() + dt.timedelta(days=RESV_HORIZON_DAYS)
                return [
                    C.ResvSet(
                        0,
                        x.id,
                        x.date.year,
                        x.date.month,
                        x.date.day,
                        x.s_h,
                        x.s_m,
                        x.e_h,
                        x.e_m,
                        x.type,
                        x.subject if x.requested_by is None else "학생 예약",
                        x.professor,
                    )
                    for x in s.scalars(
                        select(Reservation)
                        .where(
                            Reservation.room_id == rid,
                            Reservation.status == "approved",
                            Reservation.date >= lo,
                            Reservation.date <= hi,
                        )
                        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m)
                        .limit(NODE_RESV_MAX)
                    )
                ]
            if kind == "exam":
                return [
                    C.ExamSet(
                        0,
                        x.id,
                        x.date_start.year,
                        x.date_start.month,
                        x.date_start.day,
                        x.date_end.year,
                        x.date_end.month,
                        x.date_end.day,
                    )
                    for x in s.scalars(
                        select(ExamPeriod)
                        .where(ExamPeriod.room_id == rid)
                        .order_by(ExamPeriod.date_start)
                    )
                ]
            raise ValueError(kind)

    return fn
