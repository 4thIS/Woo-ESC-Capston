"""도메인 REST (spec §4.3). 변경은 같은 요청에서 lora_service.api.enqueue_* 로 outbox 에 간다."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.domain.models import Building, ExamPeriod, Reservation, Room, School, Slot
from app.lora_service import api

router = APIRouter(prefix="/api")


def get_db(request: Request):
    with request.app.state.Session() as s, s.begin():
        yield s


_DB = Depends(get_db)  # ponytail: B008 회피용 모듈 싱글턴 (ruff 권고)


def _get(s: Session, model, id_: int):
    obj = s.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__tablename__} {id_} 없음")
    return obj


def _addr(s: Session, room_id: int) -> tuple[str, int]:
    r = _get(s, Room, room_id)
    return s.get(Building, r.building_id).bld, r.room


def _modem_of(s: Session, building_id: int) -> str | None:
    return s.get(Building, building_id).modem_id


# ---- schools / buildings / rooms ----


@router.get("/schools", response_model=list[S.SchoolOut])
def list_schools(s: Session = _DB):
    return s.scalars(select(School).order_by(School.id)).all()


@router.post("/schools", response_model=S.SchoolOut)
def create_school(body: S.SchoolIn, s: Session = _DB):
    obj = School(**body.model_dump())
    s.add(obj)
    s.flush()
    return obj


@router.patch("/schools/{id}", response_model=S.SchoolOut)
def update_school(id: int, body: S.SchoolIn, s: Session = _DB):
    obj = _get(s, School, id)
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    return obj


@router.delete("/schools/{id}")
def delete_school(id: int, s: Session = _DB):
    s.delete(_get(s, School, id))
    return {"ok": True}


@router.get("/buildings", response_model=list[S.BuildingOut])
def list_buildings(s: Session = _DB):
    return s.scalars(select(Building).order_by(Building.id)).all()


@router.post("/buildings", response_model=S.BuildingOut)
def create_building(body: S.BuildingIn, s: Session = _DB):
    # ponytail: 갓 만든 건물엔 아직 방이 없어 재전송할 config 가 없다 — 모뎀은 최초 연결 때 config 를 받는다.
    obj = Building(**body.model_dump())
    s.add(obj)
    s.flush()
    return obj


@router.patch("/buildings/{id}", response_model=S.BuildingOut)
def update_building(id: int, body: S.BuildingIn, bg: BackgroundTasks, s: Session = _DB):
    obj = _get(s, Building, id)
    before = obj.modem_id
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    # FastAPI 는 background task 를 이 의존성의 teardown(커밋) *전에* 실행한다 — 그래서 여기서 직접
    # commit 해 둔다. teardown 의 with s.begin() 은 이후 남은 트랜잭션이 없으면 조용히 끝난다.
    s.commit()
    for mid in {before, obj.modem_id} - {None}:
        bg.add_task(api.config_changed, mid)
    return obj


@router.delete("/buildings/{id}")
def delete_building(id: int, bg: BackgroundTasks, s: Session = _DB):
    obj = _get(s, Building, id)
    mid = obj.modem_id
    s.delete(obj)
    s.commit()
    if mid:
        bg.add_task(api.config_changed, mid)
    return {"ok": True}


@router.get("/rooms", response_model=list[S.RoomOut])
def list_rooms(s: Session = _DB):
    return s.scalars(select(Room).order_by(Room.id)).all()


@router.post("/rooms", response_model=S.RoomOut)
def create_room(body: S.RoomIn, bg: BackgroundTasks, s: Session = _DB):
    _get(s, Building, body.building_id)
    obj = Room(**body.model_dump())
    s.add(obj)
    s.flush()
    mid = _modem_of(s, obj.building_id)  # 커밋 전에 조회 — 커밋 뒤엔 이 세션을 더 못 쓴다
    s.commit()  # background task 가 커밋된 상태를 보도록 (아래 ponytail 참고)
    if mid:
        bg.add_task(api.config_changed, mid)
    return obj


@router.patch("/rooms/{id}", response_model=S.RoomOut)
def update_room(id: int, body: S.RoomIn, bg: BackgroundTasks, s: Session = _DB):
    obj = _get(s, Room, id)
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    s.flush()
    mid = _modem_of(s, obj.building_id)
    s.commit()
    if mid:
        bg.add_task(api.config_changed, mid)
    return obj


@router.delete("/rooms/{id}")
def delete_room(id: int, bg: BackgroundTasks, s: Session = _DB):
    obj = _get(s, Room, id)
    mid = _modem_of(s, obj.building_id)
    s.delete(obj)
    s.commit()
    if mid:
        bg.add_task(api.config_changed, mid)
    return {"ok": True}


# ---- slots / reservations / exams → outbox ----


@router.get("/rooms/{id}/slots", response_model=list[S.SlotOut])
def list_slots(id: int, s: Session = _DB):
    _get(s, Room, id)
    return s.scalars(
        select(Slot).where(Slot.room_id == id).order_by(Slot.day, Slot.s_h, Slot.s_m)
    ).all()


# ponytail: 도메인·outbox 두 세션. 한 트랜잭션으로 묶으려면 api.enqueue_* 에 Session 을 넘기는 시그니처 추가.
# enqueue_* 를 도메인 write(flush/execute) 보다 먼저 부른다 — SQLite WAL 은 쓰기 락이 하나뿐이라, 도메인
# 세션이 먼저 쓰고 커밋 전에 outbox 세션이 쓰려 하면 서로 끝나기를 기다리며 busy_timeout 까지 막힌다
# (도메인 커밋은 이 요청이 끝난 뒤라 절대 안 풀린다). outbox 를 먼저 커밋시키고 도메인은 뒤따르게 한다.
# 이 순서라 enqueue 뒤 도메인 write 가 실패하면(예: IntegrityError → 500) outbox 행은 이미 커밋된 채 남는다.
@router.put("/rooms/{id}/slots", response_model=S.Enqueued)
def put_slot(id: int, body: S.SlotIn, s: Session = _DB):
    bld, room = _addr(s, id)
    obj = s.scalar(
        select(Slot).where(
            Slot.room_id == id, Slot.day == body.day, Slot.s_h == body.s_h, Slot.s_m == body.s_m
        )
    )
    if obj is None:
        obj = Slot(room_id=id)
        s.add(obj)
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    ids = api.enqueue_slot_set(
        bld,
        room,
        body.day,
        (body.s_h, body.s_m),
        (body.e_h, body.e_m),
        body.type,
        body.subject,
        body.professor,
    )
    s.flush()
    return {"outbox_ids": ids}


@router.delete("/rooms/{id}/slots/{day}/{s_h}/{s_m}", response_model=S.Enqueued)
def delete_slot(id: int, day: int, s_h: int, s_m: int, s: Session = _DB):
    bld, room = _addr(s, id)
    ids = api.enqueue_slot_del(bld, room, day, (s_h, s_m))
    s.execute(
        delete(Slot).where(Slot.room_id == id, Slot.day == day, Slot.s_h == s_h, Slot.s_m == s_m)
    )
    return {"outbox_ids": ids}


@router.delete("/rooms/{id}/slots", response_model=S.Enqueued)
def clear_day(id: int, day: int, s: Session = _DB):
    bld, room = _addr(s, id)
    ids = api.enqueue_day_clear(bld, room, day)
    s.execute(delete(Slot).where(Slot.room_id == id, Slot.day == day))
    return {"outbox_ids": ids}


@router.get("/rooms/{id}/reservations", response_model=list[S.ResvOut])
def list_resv(id: int, s: Session = _DB):
    _get(s, Room, id)
    return s.scalars(
        select(Reservation).where(Reservation.room_id == id).order_by(Reservation.date)
    ).all()


@router.post("/rooms/{id}/reservations", response_model=S.Enqueued)
def put_resv(id: int, body: S.ResvIn, s: Session = _DB):
    bld, room = _addr(s, id)
    obj = s.get(Reservation, body.id) or Reservation(id=body.id)
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    obj.room_id = id
    s.add(obj)
    ids = api.enqueue_resv_set(
        bld,
        room,
        body.id,
        body.date,
        (body.s_h, body.s_m),
        (body.e_h, body.e_m),
        body.type,
        body.subject,
        body.professor,
    )
    s.flush()
    return {"outbox_ids": ids}


@router.delete("/rooms/{id}/reservations/{resv_id}", response_model=S.Enqueued)
def delete_resv(id: int, resv_id: int, s: Session = _DB):
    bld, room = _addr(s, id)
    ids = api.enqueue_resv_del(bld, room, resv_id)
    s.execute(delete(Reservation).where(Reservation.id == resv_id, Reservation.room_id == id))
    return {"outbox_ids": ids}


@router.get("/rooms/{id}/exams", response_model=list[S.ExamOut])
def list_exams(id: int, s: Session = _DB):
    _get(s, Room, id)
    return s.scalars(
        select(ExamPeriod).where(ExamPeriod.room_id == id).order_by(ExamPeriod.date_start)
    ).all()


@router.post("/rooms/{id}/exams", response_model=S.Enqueued)
def put_exam(id: int, body: S.ExamIn, s: Session = _DB):
    bld, room = _addr(s, id)
    obj = s.get(ExamPeriod, body.id) or ExamPeriod(id=body.id)
    obj.room_id, obj.date_start, obj.date_end = id, body.date_start, body.date_end
    s.add(obj)
    ids = api.enqueue_exam_set(bld, room, body.id, body.date_start, body.date_end)
    s.flush()
    return {"outbox_ids": ids}


@router.delete("/rooms/{id}/exams/{exam_id}", response_model=S.Enqueued)
def delete_exam(id: int, exam_id: int, s: Session = _DB):
    bld, room = _addr(s, id)
    ids = api.enqueue_exam_del(bld, room, exam_id)
    s.execute(delete(ExamPeriod).where(ExamPeriod.id == exam_id, ExamPeriod.room_id == id))
    return {"outbox_ids": ids}


@router.post("/rooms/{id}/sync", response_model=S.Enqueued)
def sync_room(id: int, body: S.SyncIn, s: Session = _DB):
    bld, room = _addr(s, id)
    return {"outbox_ids": api.enqueue_full_sync(bld, room, tuple(body.kinds))}


@router.post("/rooms/{id}/cmd", response_model=S.Enqueued)
def cmd_room(id: int, body: S.CmdIn, s: Session = _DB):
    bld, room = _addr(s, id)
    return {"outbox_ids": api.enqueue_cmd(bld, room, body.cmd, bytes.fromhex(body.args_hex))}
