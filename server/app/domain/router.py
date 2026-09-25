"""도메인 REST (spec §4.3). 변경은 같은 요청에서 lora_service.api.enqueue_* 로 outbox 에 간다."""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import scope
from app.auth.deps import AdminUser
from app.auth.models import User
from app.deps import _DB
from app.domain import admin, clock, csv_import, reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, School, Slot
from app.lora_service import api

router = APIRouter(prefix="/api", dependencies=[AdminUser])  # 전부 관리자 전용 (S4a §3.3)
log = logging.getLogger(__name__)


def _addr(s: Session, room_id: int, user: User) -> tuple[str, int, str | None]:
    r = scope.get_scoped(s, Room, room_id, user.school_id)
    b = s.get(Building, r.building_id)
    return b.bld, r.room, b.modem_id


def _commit_notify(s: Session, modem_id: str | None) -> None:
    """커밋을 먼저 끝내고 허브를 깨운다 — 허브가 새 outbox 행을 바로 본다 (#9)."""
    s.commit()
    api.notify(modem_id)


def _check_building(s: Session, user: User, bld: str | None, modem_id: str | None) -> None:
    """modem_id 는 자기 학교 모뎀만, bld 는 다른 학교가 쓰면 409 (S4a §3.3 🔴4b·4c)."""
    if modem_id is not None and modem_id not in scope.modem_ids(s, user.school_id):
        raise HTTPException(404, f"modems {modem_id} 없음")
    if bld is not None:
        other = s.scalar(
            select(Building.id)
            .where(Building.bld == bld, Building.school_id != user.school_id)
            .limit(1)
        )
        if other is not None:
            raise HTTPException(409, f"bld '{bld}' 는 다른 학교가 쓰고 있습니다 (공중 주소는 전역)")


def _modem_of(s: Session, building_id: int) -> str | None:
    return s.get(Building, building_id).modem_id


ID_MAX = 65535  # resvId/examId u16 (v2 §3). 테스트가 monkeypatch 로 낮춘다
_ID_LOCK = threading.Lock()  # 채번~커밋을 직렬화 — 단일 워커(README)라 프로세스 락으로 충돌이 없다


def _free_id(s: Session, model) -> int:
    """1..ID_MAX 중 비어 있는 최소값 (S4b §2.5). 전역 PK 라 방과 무관."""
    used = set(s.scalars(select(model.id)))
    for i in range(1, ID_MAX + 1):
        if i not in used:
            return i
    raise HTTPException(409, "id 소진 — 지난 예약·시험기간을 정리하세요")


def _existing_same_room(s: Session, model, obj_id: int, room_id: int):
    """id 지정 수정은 같은 방의 기존 행만 (S4a §3.3 🔴4a). 다른 방(=다른 학교 포함) 행이면 409.
    없는 id 지정은 그 id 로 새로 만든다 — 기존 S2 호출·테스트 호환, 탈취 위험은 기존 행에만 있다."""
    obj = s.get(model, obj_id)
    if obj is not None and obj.room_id != room_id:
        raise HTTPException(409, "id 가 다른 방의 것입니다 — 방을 옮기려면 삭제 후 다시 만드세요")
    if obj is not None and getattr(obj, "status", "approved") != "approved":
        raise HTTPException(409, "신청 상태 예약은 승인 절차로 처리하세요")
    return obj


# ---- schools / buildings / rooms ----


@router.get("/schools", response_model=list[S.SchoolOut])
def list_schools(user: User = AdminUser, s: Session = _DB):
    return s.scalars(select(School).where(School.id == user.school_id)).all()


# 학교 생성·삭제는 CLI 전용 (S4a §3.3). PATCH 는 name 만.
@router.patch("/schools/{id}", response_model=S.SchoolOut)
def update_school(id: int, body: S.SchoolPatch, user: User = AdminUser, s: Session = _DB):
    obj = scope.get_scoped(s, School, id, user.school_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    s.flush()
    return obj


@router.get("/buildings", response_model=list[S.BuildingOut])
def list_buildings(user: User = AdminUser, s: Session = _DB):
    return s.scalars(
        select(Building).where(Building.school_id == user.school_id).order_by(Building.id)
    ).all()


@router.post("/buildings", response_model=S.BuildingOut)
def create_building(body: S.BuildingIn, user: User = AdminUser, s: Session = _DB):
    if body.school_id != user.school_id:
        raise HTTPException(404, f"schools {body.school_id} 없음")
    _check_building(s, user, body.bld, body.modem_id)
    # 참고: 갓 만든 건물엔 아직 방이 없어 재전송할 config 가 없다 — 모뎀은 최초 연결 때 config 를 받는다.
    obj = Building(**body.model_dump())
    s.add(obj)
    s.flush()
    return obj


@router.patch("/buildings/{id}", response_model=S.BuildingOut)
def update_building(
    id: int, body: S.BuildingPatch, bg: BackgroundTasks, user: User = AdminUser, s: Session = _DB
):
    obj = scope.get_scoped(s, Building, id, user.school_id)
    data = body.model_dump(exclude_unset=True)
    _check_building(s, user, data.get("bld"), data.get("modem_id"))
    before = obj.modem_id
    bld = obj.bld
    rooms = list(s.scalars(select(Room.room).where(Room.building_id == obj.id)))
    for k, v in data.items():
        setattr(obj, k, v)
    # FastAPI 는 background task 를 이 의존성의 teardown(커밋) *전에* 실행한다 — 그래서 여기서 직접
    # commit 해 둔다. teardown 의 with s.begin() 은 이후 남은 트랜잭션이 없으면 조용히 끝난다.
    s.commit()
    if obj.modem_id != before:
        # 커밋 뒤에 부른다 — outbox 재지정 트랜잭션이 방금 끝난 도메인 쓰기 락과 경합하지 않도록.
        api.reassign_queued(bld, rooms, obj.modem_id)
    for mid in {before, obj.modem_id} - {None}:
        bg.add_task(api.config_changed, mid)
    return obj


@router.delete("/buildings/{id}")
def delete_building(id: int, bg: BackgroundTasks, user: User = AdminUser, s: Session = _DB):
    obj = scope.get_scoped(s, Building, id, user.school_id)
    mid = obj.modem_id
    s.delete(obj)
    s.commit()
    if mid:
        bg.add_task(api.config_changed, mid)
    return {"ok": True}


# ---- 건물 단위 조회 (S4b §2.6, 이슈 #36) — 쓰기는 /rooms/{id}/… 그대로 ----


def _rooms_of(s: Session, building_id: int, user: User):
    scope.get_scoped(s, Building, building_id, user.school_id)
    return select(Room.id).where(Room.building_id == building_id)


@router.get("/buildings/{id}/slots", response_model=list[S.SlotWithRoom])
def building_slots(id: int, user: User = AdminUser, s: Session = _DB):
    return s.scalars(
        select(Slot)
        .where(Slot.room_id.in_(_rooms_of(s, id, user)))
        .order_by(Slot.room_id, Slot.day, Slot.s_h, Slot.s_m)
    ).all()


@router.get("/buildings/{id}/reservations", response_model=list[S.ResvWithRoom])
def building_reservations(id: int, user: User = AdminUser, s: Session = _DB):
    return admin.resv_with_room_rows(
        s,
        select(Reservation)
        .where(Reservation.room_id.in_(_rooms_of(s, id, user)))
        .order_by(Reservation.room_id, Reservation.date, Reservation.s_h, Reservation.s_m),
    )


@router.get("/buildings/{id}/exams", response_model=list[S.ExamWithRoom])
def building_exams(id: int, user: User = AdminUser, s: Session = _DB):
    return s.scalars(
        select(ExamPeriod)
        .where(ExamPeriod.room_id.in_(_rooms_of(s, id, user)))
        .order_by(ExamPeriod.room_id, ExamPeriod.date_start)
    ).all()


@router.get("/buildings/{id}/outbox", response_model=list[S.FailedOut])
def building_outbox(
    id: int,
    state: Literal["queued", "dispatched", "acked", "failed", "cancelled"] | None = None,
    limit: int = Query(200, ge=1, le=500),
    user: User = AdminUser,
    s: Session = _DB,
):
    scope.get_scoped(s, Building, id, user.school_id)
    return admin.building_outbox(s, id, user.school_id, state, limit)


@router.get("/rooms", response_model=list[S.RoomOut])
def list_rooms(user: User = AdminUser, s: Session = _DB):
    return s.scalars(
        select(Room).join(Building).where(Building.school_id == user.school_id).order_by(Room.id)
    ).all()


@router.post("/rooms", response_model=S.RoomOut)
def create_room(body: S.RoomIn, bg: BackgroundTasks, user: User = AdminUser, s: Session = _DB):
    scope.get_scoped(s, Building, body.building_id, user.school_id)
    obj = Room(**body.model_dump())
    s.add(obj)
    s.flush()
    mid = _modem_of(s, obj.building_id)  # 커밋 전에 조회 — 커밋 뒤엔 이 세션을 더 못 쓴다
    s.commit()  # background task 가 커밋된 상태를 보도록 (아래 ponytail 참고)
    if mid:
        bg.add_task(api.config_changed, mid)
    return obj


@router.patch("/rooms/{id}", response_model=S.RoomOut)
def update_room(
    id: int, body: S.RoomPatch, bg: BackgroundTasks, user: User = AdminUser, s: Session = _DB
):
    obj = scope.get_scoped(s, Room, id, user.school_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    s.flush()
    mid = _modem_of(s, obj.building_id)
    s.commit()
    if mid:
        bg.add_task(api.config_changed, mid)
    return obj


@router.delete("/rooms/{id}")
def delete_room(id: int, bg: BackgroundTasks, user: User = AdminUser, s: Session = _DB):
    obj = scope.get_scoped(s, Room, id, user.school_id)
    mid = _modem_of(s, obj.building_id)
    s.delete(obj)
    s.commit()
    if mid:
        bg.add_task(api.config_changed, mid)
    return {"ok": True}


# ---- slots / reservations / exams → outbox ----


@router.get("/rooms/{id}/slots", response_model=list[S.SlotOut])
def list_slots(id: int, user: User = AdminUser, s: Session = _DB):
    scope.get_scoped(s, Room, id, user.school_id)
    return s.scalars(
        select(Slot).where(Slot.room_id == id).order_by(Slot.day, Slot.s_h, Slot.s_m)
    ).all()


# 버전·outbox·도메인 write 는 같은 세션(#9). 핸들러가 커밋한 뒤 허브에 알린다 — BackgroundTasks 는
# get_db 커밋 전에 돌므로 쓰지 않는다.
@router.put("/rooms/{id}/slots", response_model=S.Enqueued)
def put_slot(id: int, body: S.SlotIn, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    obj = s.scalar(
        select(Slot).where(
            Slot.room_id == id, Slot.day == body.day, Slot.s_h == body.s_h, Slot.s_m == body.s_m
        )
    )
    if obj is not None and obj.source > body.source:
        raise HTTPException(409, f"source {obj.source} 슬롯은 source ≥ {obj.source} 로만 수정")
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
        session=s,
    )
    _commit_notify(s, mid)
    return {"outbox_ids": ids}


@router.delete("/rooms/{id}/slots/{day}/{s_h}/{s_m}", response_model=S.Enqueued)
def delete_slot(id: int, day: int, s_h: int, s_m: int, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    s.execute(
        delete(Slot).where(Slot.room_id == id, Slot.day == day, Slot.s_h == s_h, Slot.s_m == s_m)
    )
    ids = api.enqueue_slot_del(bld, room, day, (s_h, s_m), session=s)
    _commit_notify(s, mid)
    return {"outbox_ids": ids}


@router.delete("/rooms/{id}/slots", response_model=S.Enqueued)
def clear_day(id: int, day: int, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    s.execute(delete(Slot).where(Slot.room_id == id, Slot.day == day))
    ids = api.enqueue_day_clear(bld, room, day, session=s)
    _commit_notify(s, mid)
    return {"outbox_ids": ids}


@router.get("/rooms/{id}/reservations", response_model=list[S.ResvWithRoom])
def list_resv(id: int, user: User = AdminUser, s: Session = _DB):
    scope.get_scoped(s, Room, id, user.school_id)
    return admin.resv_with_room_rows(
        s,
        select(Reservation)
        .where(Reservation.room_id == id)
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m),
    )


@router.post("/rooms/{id}/reservations", response_model=S.Enqueued)
def put_resv(id: int, body: S.ResvIn, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    with (
        _ID_LOCK
    ):  # 확인(채번·같은 방 검사) → insert → 커밋까지 한 덩어리 (다음 요청은 커밋된 행을 본다)
        if body.id is not None:  # 없는 id 지정 생성도 동시 채번과 겹치지 않게 락 안 (r2 ⚪)
            return _write_resv(
                s,
                id,
                bld,
                room,
                mid,
                body,
                body.id,
                _existing_same_room(s, Reservation, body.id, id),
            )
        return _write_resv(s, id, bld, room, mid, body, _free_id(s, Reservation), None)


def _write_resv(
    s, room_id, bld, room, mid, body: S.ResvIn, rid: int, obj: Reservation | None
) -> dict:
    obj = obj or Reservation(id=rid, room_id=room_id)
    old_end = (obj.date, obj.e_h, obj.e_m)  # 노드가 가진 옛 항목의 끝 (새 행이면 None 들)
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(obj, k, v)
    s.add(obj)
    now = clock.local_now()
    today = now.date()
    if reserve.in_window(body.date, today):
        if reserve.room_full(s, room_id, today, exclude_id=rid):
            raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)")
        ids = reserve.push_set(s, obj)
    else:  # 창 밖으로 옮겼으면 노드의 옛 날짜 항목을 지운다 (r3, 리뷰 🔴1c)
        ids = reserve.push_del(s, obj, now, end=old_end if old_end[0] else None)
    _commit_notify(s, mid)
    return {"outbox_ids": ids, "id": rid}


@router.delete("/rooms/{id}/reservations/{resv_id}", response_model=S.Enqueued)
def delete_resv(id: int, resv_id: int, user: User = AdminUser, s: Session = _DB):
    *_, mid = _addr(s, id, user)
    with _ID_LOCK:  # 예약 쓰기는 읽기~커밋 전부 같은 락 — 동시 승인·승격과 엇갈리지 않게
        r = s.get(Reservation, resv_id)
        if r is None or r.room_id != id:  # 멱등 — 없는 id 에 RESV_DEL 을 보내지 않는다
            return {"outbox_ids": []}
        # 노드로 보낸 적 있는 것만 (r2: 신청·창 밖 예약엔 DEL 없음)
        ids = reserve.push_del(s, r, clock.local_now())
        s.delete(r)
        _commit_notify(s, mid)
    return {"outbox_ids": ids}


@router.get("/rooms/{id}/exams", response_model=list[S.ExamOut])
def list_exams(id: int, user: User = AdminUser, s: Session = _DB):
    scope.get_scoped(s, Room, id, user.school_id)
    return s.scalars(
        select(ExamPeriod).where(ExamPeriod.room_id == id).order_by(ExamPeriod.date_start)
    ).all()


@router.post("/rooms/{id}/exams", response_model=S.Enqueued)
def put_exam(id: int, body: S.ExamIn, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    with _ID_LOCK:
        if body.id is not None:
            return _write_exam(
                s,
                id,
                bld,
                room,
                mid,
                body,
                body.id,
                _existing_same_room(s, ExamPeriod, body.id, id),
            )
        return _write_exam(s, id, bld, room, mid, body, _free_id(s, ExamPeriod), None)


def _write_exam(
    s, room_id, bld, room, mid, body: S.ExamIn, eid: int, obj: ExamPeriod | None
) -> dict:
    obj = obj or ExamPeriod(id=eid, room_id=room_id)
    obj.date_start, obj.date_end = body.date_start, body.date_end
    s.add(obj)
    ids = api.enqueue_exam_set(bld, room, eid, body.date_start, body.date_end, session=s)
    _commit_notify(s, mid)
    return {"outbox_ids": ids, "id": eid}


@router.delete("/rooms/{id}/exams/{exam_id}", response_model=S.Enqueued)
def delete_exam(id: int, exam_id: int, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    with _ID_LOCK:  # 같은 id 수정(put_exam)의 읽기~커밋 사이에 끼어들면 StaleDataError (#48 🟡2)
        s.execute(delete(ExamPeriod).where(ExamPeriod.id == exam_id, ExamPeriod.room_id == id))
        ids = api.enqueue_exam_del(bld, room, exam_id, session=s)
        _commit_notify(s, mid)
    return {"outbox_ids": ids}


@router.post("/rooms/{id}/sync", response_model=S.Enqueued)
def sync_room(id: int, body: S.SyncIn, user: User = AdminUser, s: Session = _DB):
    bld, room, _mid = _addr(s, id, user)
    return {"outbox_ids": api.enqueue_full_sync(bld, room, tuple(body.kinds))}


@router.post("/rooms/{id}/cmd", response_model=S.Enqueued)
def cmd_room(id: int, body: S.CmdIn, user: User = AdminUser, s: Session = _DB):
    bld, room, mid = _addr(s, id, user)
    ids = api.enqueue_cmd(bld, room, body.cmd, bytes.fromhex(body.args_hex), session=s)
    _commit_notify(s, mid)
    return {"outbox_ids": ids}


IMPORT_MAX_BYTES = 1024 * 1024


@router.post(
    "/import/slots",
    response_model=S.ImportSummary,
    responses={400: {"model": S.ImportErrors}, 413: {}, 500: {}},
)
def import_slots(
    raw: bytes = Body(..., media_type="text/csv"),
    dry_run: bool = False,
    user: User = AdminUser,
    s: Session = _DB,
):
    """시간표 CSV (S2b §4). 본문 = CSV 텍스트(text/csv). 전체 검증 → 적용 → commit → 방마다 콘텐츠 FILE.
    동기 함수 — DB 작업은 threadpool 에서 돌아 같은 프로세스의 asyncio WS 허브를 막지 않는다."""
    if len(raw) > IMPORT_MAX_BYTES:
        raise HTTPException(413, f"{IMPORT_MAX_BYTES} B 초과")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(400, "UTF-8 로 저장하세요 (엑셀: CSV UTF-8)") from e
    rows, errors = csv_import.parse(text, s, school_id=user.school_id)
    if errors:
        return JSONResponse(status_code=400, content={"errors": [asdict(e) for e in errors]})
    sm = csv_import.apply(rows, s, dry_run=dry_run)
    out = {k: v for k, v in asdict(sm).items() if k != "changed"}
    if dry_run:
        return out | {"outbox_ids": []}
    s.commit()  # RecordProvider 가 커밋된 슬롯을 읽어야 FILE 내용이 새 것이다 (S2b §3)
    ids: list[int] = []
    for bld, room in sm.changed:
        try:
            ids += api.enqueue_file_replace(bld, room, "schedule")
        except Exception as e:  # DB 는 이미 반영됨 — 관리자가 sync 로 복구
            log.exception("FILE 큐잉 실패 %s%s — DB 는 반영됨", bld, room)
            raise HTTPException(
                500,
                f"FILE 큐잉 실패 ({bld}{room}). DB 는 반영됨 — POST /api/rooms/{{id}}/sync 로 재전송",
            ) from e
    return out | {"outbox_ids": ids}
