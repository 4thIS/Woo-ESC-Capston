"""관리자 집계·조인 조회 (S4b). 세션과 school_id 를 받아 dict 목록을 돌려준다 — 라우터가 얇게 감싼다.
terminal_status·outbox·modems·pending_devices 는 여기서 ORM 읽기만 한다. lora_service.api 는 부르지 않는다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import scope
from app.auth.models import User
from app.db import utcnow
from app.domain.models import Building, Room
from app.lora_service.models import Modem, Outbox, PendingDevice, TerminalStatus


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


UNSEEN_HOURS = 48  # STATUS 는 일 1회 — 24 h 면 오탐 (S4b §2.1)
FAILED_DAYS_DEFAULT = 7
WARNING_ORDER = ("unseen", "low_batt", "resync", "clock_stale")
_TS_FIELDS = (
    "modem_id",
    "mac",
    "fw",
    "batt_mv",
    "rssi",
    "snr",
    "sched_ver",
    "resv_ver",
    "exam_ver",
    "ident_ver",
    "layout",
    "uptime_h",
    "last_seen_at",
    "last_ack_at",
    "last_status_at",
)


def expected_nodes(
    s: Session, school_id: int, building_id: int | None = None, now: dt.datetime | None = None
) -> list[dict]:
    """학교의 기대 노드(rooms × units) 에 terminal_status 를 LEFT JOIN 하고 경고를 판정한다."""
    now = now or utcnow()
    cutoff = now - dt.timedelta(hours=UNSEEN_HOURS)
    q = (
        select(Room, Building)
        .join(Building, Room.building_id == Building.id)
        .where(Building.school_id == school_id)
        .order_by(Building.bld, Room.room)
    )
    if building_id is not None:
        q = q.where(Building.id == building_id)
    pairs = s.execute(q).all()
    blds = {b.bld for _, b in pairs}
    mids = scope.modem_ids(s, school_id)
    status = {
        (t.bld, t.room, t.unit): t
        for t in s.scalars(
            select(TerminalStatus).where(
                TerminalStatus.bld.in_(blds),
                TerminalStatus.modem_id.is_(None) | TerminalStatus.modem_id.in_(mids),
            )
        )
    }  # bld 재사용 뒤 남은 옛 학교 소유 status 행은 숨긴다 — /api/lora/status 와 같은 규칙
    out: list[dict] = []
    for room, b in pairs:
        for unit in range(1, room.units + 1):
            t = status.get((b.bld, room.room, unit))
            unseen = t is None or t.last_seen_at is None or t.last_seen_at < cutoff
            flags = {
                "unseen": unseen,
                "low_batt": bool(t and t.low_batt),
                "resync": bool(t and t.sync_state == "resync"),
                "clock_stale": bool(t and t.clock_stale),
            }
            out.append(
                {
                    "room_id": room.id,
                    "building_id": b.id,
                    "building": b.name,
                    "bld": b.bld,
                    "room": room.room,
                    "unit": unit,
                    **{f: getattr(t, f) if t else None for f in _TS_FIELDS},
                    "clock_stale": flags["clock_stale"],
                    "low_batt": flags["low_batt"],
                    "sync_state": t.sync_state if t else "unknown",
                    "warnings": [w for w in WARNING_ORDER if flags[w]],
                }
            )
    return out


def failed_outbox(
    s: Session,
    school_id: int,
    days: int = FAILED_DAYS_DEFAULT,
    limit: int | None = None,
    now: dt.datetime | None = None,
) -> list[dict]:
    """최근 days 일 failed outbox 에 방·건물 조인. 방을 못 찾는 행(삭제된 방)은 빠진다."""
    cutoff = (now or utcnow()) - dt.timedelta(days=days)
    mids = scope.modem_ids(s, school_id)
    q = (
        select(Outbox, Room.id, Building.name)
        .join(Building, and_(Building.bld == Outbox.bld, Building.school_id == school_id))
        .join(Room, and_(Room.building_id == Building.id, Room.room == Outbox.room))
        .where(Outbox.state == "failed", Outbox.finished_at >= cutoff)
        .where(
            Outbox.modem_id.is_(None) | Outbox.modem_id.in_(mids)
        )  # bld 재사용 뒤 옛 학교 행 숨김
        .where(
            (Outbox.last_error.is_(None)) | (Outbox.last_error != "cancelled")
        )  # 관리자 취소분은 실패가 아니다
        .order_by(Outbox.finished_at.desc(), Outbox.id.desc())
    )
    if limit is not None:
        q = q.limit(limit)
    return _outbox_rows(s, q)


PREVIEW_DEFAULT = 5
PREVIEW_MAX = 20
_MIN = dt.datetime.min  # noqa: DTZ901 — 앱 전역이 naive UTC (app.db.utcnow)


def _bucket(items: list, preview: int) -> dict:
    return {"count": len(items), "items": items[:preview]}


def summary(
    s: Session, school_id: int, preview: int = PREVIEW_DEFAULT, now: dt.datetime | None = None
) -> dict:
    """S4b §2.3 — 경고 8종 카운트 + 미리보기, 총계. 요청마다 계산(캐시 없음)."""
    now = now or utcnow()
    nodes = expected_nodes(s, school_id, now=now)
    by_seen = sorted(nodes, key=lambda n: n["last_seen_at"] or _MIN)  # 보고 없음(None) 먼저
    modems = s.scalars(
        select(Modem).where(Modem.school_id == school_id).order_by(Modem.modem_id)
    ).all()
    bnames: dict[str, list[str]] = {}
    for mid, bname in s.execute(
        select(Building.modem_id, Building.name).where(Building.school_id == school_id)
    ).all():
        bnames.setdefault(mid, []).append(bname)
    for names in bnames.values():
        names.sort()
    offline = [
        {
            "modem_id": m.modem_id,
            "last_seen_at": m.last_seen_at,
            "buildings": bnames.get(m.modem_id, []),
        }
        for m in modems
        if not m.connected
    ]
    failed = failed_outbox(s, school_id, FAILED_DAYS_DEFAULT, None, now)
    mids = {m.modem_id for m in modems}
    pending = [
        S.PendingOut.model_validate(p).model_dump()
        for p in s.scalars(
            select(PendingDevice)
            .where(PendingDevice.modem_id.in_(mids))
            .order_by(PendingDevice.first_seen_at, PendingDevice.mac)
        )
    ]
    approvals = [
        S.UserOut.model_validate(u).model_dump()
        for u in s.scalars(
            select(User)
            .where(User.school_id == school_id, User.status == "pending_approval")
            .order_by(User.created_at, User.email)
        )
    ]
    return {
        "as_of": now,
        "totals": {
            "buildings": s.scalar(
                select(func.count()).select_from(Building).where(Building.school_id == school_id)
            ),
            "rooms": len({n["room_id"] for n in nodes}),
            "nodes": len(nodes),
            "modems": len(modems),
        },
        "warnings": {
            "modem_offline": _bucket(offline, preview),
            **{
                w: _bucket([n for n in by_seen if w in n["warnings"]], preview)
                for w in WARNING_ORDER
            },
            "failed": _bucket(failed, preview),
            "pending_devices": _bucket(pending, preview),
            "pending_approval": _bucket(approvals, preview),
        },
    }
