"""관리자 집계·조인 조회 (S4b). 세션과 school_id 를 받아 dict 목록을 돌려준다 — 라우터가 얇게 감싼다.
terminal_status·outbox·modems·pending_devices 는 여기서 ORM 읽기만 한다. lora_service.api 는 부르지 않는다."""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import scope
from app.domain.models import Building, Room
from app.lora_service.models import Outbox


def _outbox_rows(s: Session, q) -> list[dict]:
    """select(Outbox, Room.id, Building.name) 결과 → FailedOut dict."""
    return [
        S.OutboxOut.model_validate(o).model_dump() | {"room_id": rid, "building": bname}
        for o, rid, bname in s.execute(q).all()
    ]


def building_outbox(
    s: Session, building_id: int, school_id: int, state: str | None = None, limit: int = 200
) -> list[dict]:
    # bld 재사용(건물 삭제 뒤 같은 글자로 재생성) 뒤 남은 옛 학교(모뎀 소속)의 행을 숨긴다 —
    # /api/lora/outbox 와 같은 규칙(S4a 리뷰 🟡). NULL 은 통과.
    mids = scope.modem_ids(s, school_id)
    q = (
        select(Outbox, Room.id, Building.name)
        .join(Building, and_(Building.bld == Outbox.bld, Building.id == building_id))
        .join(Room, and_(Room.building_id == Building.id, Room.room == Outbox.room))
        .where(Outbox.modem_id.is_(None) | Outbox.modem_id.in_(mids))
        .order_by(Outbox.id.desc())
        .limit(limit)
    )
    if state is not None:
        q = q.where(Outbox.state == state)
    return _outbox_rows(s, q)
