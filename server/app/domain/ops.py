"""도메인 쓰기 — 커밋·notify 를 하지 않는다 (AI 비서 spec §5.1).

관리자 라우터 = 이 함수 + 커밋 + notify. AI 비서 미리보기 = 이 함수 + rollback, 적용 = 이 함수 + 커밋 + notify.
그래서 미리보기에서 본 결과와 실제 적용 결과가 같은 코드에서 나온다.

채번(_free_id)·같은 방 검사(_existing_same_room)·ID_MAX·_ID_LOCK 은 router 에 그대로 둔다 —
tests/test_admin_ids.py 가 router 모듈 속성을 바꿔 끼운다. _ID_LOCK 은 호출자가 잡는다."""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.domain import reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service import api


def room_addr(s: Session, room_id: int) -> tuple[str, int, str | None]:
    """(bld, room, modem_id). 범위 검사는 호출자가 먼저 한다."""
    r = s.get(Room, room_id)
    b = s.get(Building, r.building_id)
    return b.bld, r.room, b.modem_id


def put_slot(s: Session, room_id: int, bld: str, room: int, body: S.SlotIn) -> list[int]:
    """슬롯 한 개 쓰기 + outbox (옛 router._put_slot 그대로)."""
    obj = s.scalar(
        select(Slot).where(
            Slot.room_id == room_id,
            Slot.day == body.day,
            Slot.s_h == body.s_h,
            Slot.s_m == body.s_m,
        )
    )
    if obj is not None and obj.source > body.source:
        raise HTTPException(409, f"source {obj.source} 슬롯은 source ≥ {obj.source} 로만 수정")
    if obj is None:
        obj = Slot(room_id=room_id)
        s.add(obj)
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    return api.enqueue_slot_set(
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


def delete_slot(
    s: Session, room_id: int, bld: str, room: int, day: int, s_h: int, s_m: int
) -> list[int]:
    s.execute(
        delete(Slot).where(
            Slot.room_id == room_id, Slot.day == day, Slot.s_h == s_h, Slot.s_m == s_m
        )
    )
    return api.enqueue_slot_del(bld, room, day, (s_h, s_m), session=s)


def clear_day(s: Session, room_id: int, bld: str, room: int, day: int) -> list[int]:
    s.execute(delete(Slot).where(Slot.room_id == room_id, Slot.day == day))
    return api.enqueue_day_clear(bld, room, day, session=s)


def write_resv(
    s: Session,
    room_id: int,
    body: S.ResvIn,
    rid: int,
    obj: Reservation | None,
    now_local: dt.datetime,
) -> list[int]:
    """예약 쓰기 (옛 router._write_resv 에서 커밋·notify 를 뺀 것)."""
    obj = obj or Reservation(id=rid, room_id=room_id)
    old_end = (obj.date, obj.e_h, obj.e_m)  # 노드가 가진 옛 항목의 끝 (새 행이면 None 들)
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(obj, k, v)
    s.add(obj)
    today = now_local.date()
    if reserve.in_window(body.date, today):
        if reserve.room_full(s, room_id, today, exclude_id=rid):
            raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)")
        return reserve.push_set(s, obj)
    # 창 밖으로 옮겼으면 노드의 옛 날짜 항목을 지운다 (r3, 리뷰 🔴1c)
    return reserve.push_del(s, obj, now_local, end=old_end if old_end[0] else None)


def delete_resv(s: Session, room_id: int, resv_id: int, now_local: dt.datetime) -> list[int] | None:
    """없거나 다른 방 행이면 None — 멱등, 없는 id 에 RESV_DEL 을 보내지 않는다."""
    r = s.get(Reservation, resv_id)
    if r is None or r.room_id != room_id:
        return None
    ids = reserve.push_del(s, r, now_local)  # 노드로 보낸 적 있는 것만 (r2)
    s.delete(r)
    return ids


def write_exam(
    s: Session,
    room_id: int,
    bld: str,
    room: int,
    body: S.ExamIn,
    eid: int,
    obj: ExamPeriod | None,
) -> list[int]:
    obj = obj or ExamPeriod(id=eid, room_id=room_id)
    obj.date_start, obj.date_end = body.date_start, body.date_end
    s.add(obj)
    return api.enqueue_exam_set(bld, room, eid, body.date_start, body.date_end, session=s)


def delete_exam(s: Session, room_id: int, bld: str, room: int, exam_id: int) -> list[int]:
    s.execute(delete(ExamPeriod).where(ExamPeriod.id == exam_id, ExamPeriod.room_id == room_id))
    return api.enqueue_exam_del(bld, room, exam_id, session=s)
