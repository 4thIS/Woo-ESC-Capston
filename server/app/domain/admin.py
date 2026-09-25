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
from app.domain import clock, reserve
from app.domain.models import Building, Reservation, Room
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


def _mine_out(s: Session, r: Reservation) -> dict:
    """S10 §4.1/§4.2 학생·관리자 예약 응답 공용 (student_router 도 이걸 쓴다 — 순환 회피용 위치)."""
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


def _requester(u: User | None) -> dict | None:
    return {"email": u.email, "name": u.name, "student_no": u.student_no} if u else None


def resv_admin_out(s: Session, r: Reservation) -> dict:
    u = s.get(User, r.requested_by) if r.requested_by else None
    return {**_mine_out(s, r), "requester": _requester(u), "pushed_at": r.pushed_at}


def resv_with_room_rows(s: Session, q) -> list[dict]:
    """select(Reservation) → ResvWithRoom dict (web A2). 신청자는 한 쿼리로 읽는다 — 건물 전체가 수백 행."""
    rows = s.scalars(q).all()
    emails = {r.requested_by for r in rows if r.requested_by}
    users = {u.email: u for u in s.scalars(select(User).where(User.email.in_(emails)))}
    return [
        {
            **S.ResvOut.model_validate(r).model_dump(),
            "room_id": r.room_id,
            "requester": _requester(users.get(r.requested_by)),
            "pushed_at": r.pushed_at,
        }
        for r in rows
    ]


def pending_reservations(s: Session, school_id: int, now_local: dt.datetime) -> list[dict]:
    q = (
        select(Reservation)
        .join(Room, Room.id == Reservation.room_id)
        .join(Building, Building.id == Room.building_id)
        .where(Building.school_id == school_id, Reservation.status == "requested")
        .order_by(
            Reservation.requested_at, Reservation.id
        )  # 같은 시각이면 id — SQLite 동순위 순서는 정의되지 않음
    )
    # 시작 지난 신청은 승인할 수 없다(409) — 04:00 만료 전까지 경고에 남기지 않는다
    return [resv_admin_out(s, r) for r in s.scalars(q) if reserve.start_local(r) > now_local]


def summary(
    s: Session, school_id: int, preview: int = PREVIEW_DEFAULT, now: dt.datetime | None = None
) -> dict:
    """S4b §2.3 — 경고 8종 카운트 + 미리보기, 총계. 요청마다 계산(캐시 없음)."""
    # 예약은 KST·clock 기준 — 주입된 now 가 있으면 그것을 쓴다
    now_local = clock.to_local(now) if now else clock.local_now()
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
            "pending_reservations": _bucket(pending_reservations(s, school_id, now_local), preview),
        },
    }
