import datetime as dt

from sqlalchemy import func, select

from app import schemas as S
from app.domain import ops
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service.models import Outbox, RoomVersion

NOW = dt.datetime(2026, 11, 25, 10, 0)  # noqa: DTZ001 — KST naive (ops 는 지역 시각을 받는다)
SLOT = S.SlotIn(day=1, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="자료구조", professor="김")
RESV = S.ResvIn(
    date=dt.date(2026, 11, 27), s_h=15, s_m=0, e_h=18, e_m=0, type=5, subject="특강", professor=""
)
EXAM = S.ExamIn(date_start=dt.date(2026, 12, 15), date_end=dt.date(2026, 12, 19))


def _room(db) -> int:
    """FakeTopo 의 E301(유닛 2, 모뎀 m1) 과 같은 방을 DB 에 — enqueue 가 유닛마다 행을 만든다."""
    with db() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=301, units=2)
        s.add(r)
        s.flush()
        return r.id


def _n(s, model) -> int:
    return s.scalar(select(func.count()).select_from(model))


def test_writes_flush_but_do_not_commit(app, school, db):
    rid = _room(db)
    with db() as s:
        assert ops.room_addr(s, rid) == ("E", 301, None)
        ids = ops.put_slot(s, rid, "E", 301, SLOT)
        ids += ops.write_resv(s, rid, RESV, 1, None, NOW)
        ids += ops.write_exam(s, rid, "E", 301, EXAM, 1, None)
        s.flush()
        assert len(ids) == 6  # 3 작업 × 유닛 2
        assert (_n(s, Slot), _n(s, Reservation), _n(s, ExamPeriod)) == (1, 1, 1)
        s.rollback()
    with db() as s:  # rollback 하면 도메인 행도 outbox·버전도 남지 않는다
        assert (_n(s, Slot), _n(s, Reservation), _n(s, ExamPeriod)) == (0, 0, 0)
        assert _n(s, Outbox) == 0 and _n(s, RoomVersion) == 0


def test_deletes_and_idempotent_resv(app, school, db):
    rid = _room(db)
    with db() as s, s.begin():
        ops.put_slot(s, rid, "E", 301, SLOT)
        ops.write_resv(s, rid, RESV, 1, None, NOW)
        ops.write_exam(s, rid, "E", 301, EXAM, 1, None)
    with db() as s, s.begin():
        assert ops.delete_resv(s, rid, 99, NOW) is None  # 없는 id — RESV_DEL 안 보냄
        assert len(ops.delete_resv(s, rid, 1, NOW)) == 2  # 노드로 보낸 예약 → RESV_DEL × 유닛 2
        assert len(ops.delete_slot(s, rid, "E", 301, 1, 9, 0)) == 2
        assert len(ops.delete_exam(s, rid, "E", 301, 1)) == 2
        assert len(ops.clear_day(s, rid, "E", 301, 2)) == 2
    with db() as s:
        assert (_n(s, Slot), _n(s, Reservation), _n(s, ExamPeriod)) == (0, 0, 0)
