"""학생 예약 제약·전이 (S10 §2.4·§4). 라우터(학생·관리자)가 공유.
outbox 는 approve·cancel 에서만, 호출자 세션으로(enqueue_*(session=s)) — 커밋·notify 는 호출자 (S2c).
_ID_LOCK 은 호출자가 잡는다 — 여기서 잡으면 비재진입 락이라 교착."""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.models import User
from app.domain import clock, room_state
from app.domain.models import Building, Reservation, Room, Slot
from app.domain.topology import NODE_RESV_MAX, RESV_HORIZON_DAYS
from app.lora_service import api

MAX_ACTIVE = 3
MIN_MIN, MAX_MIN = 15, 120
OPEN_MIN, CLOSE_MIN = 9 * 60, 21 * 60  # 운영 시간 KST (S10 §2.6) — analytics 도 이 값을 쓴다
STEP_MIN = 5  # StudentResvIn 의 s_m·e_m multiple_of=5
STUDENT_LABEL = "학생 예약"  # 문 앞 e-Paper 는 공개 — 학생이 적은 목적은 싣지 않는다
CHECKIN_BEFORE, CHECKIN_AFTER = 10, 15  # 분
STUDENT_TYPE = 6  # 대여
_LIVE = ("approved", "requested")
STATUSES = frozenset(
    ("requested", "approved", "rejected", "cancelled", "expired")
)  # ck_resv_status


def parse_statuses(status: str) -> list[str]:
    """쉼표 목록 ?status= → 목록. 모르는 값·빈 값은 422 (오타가 조용히 빈 목록이 되지 않게)."""
    states = status.split(",")
    if not all(x in STATUSES for x in states):
        raise HTTPException(422, f"status 는 {', '.join(sorted(STATUSES))} 중 쉼표 목록")
    return states


def start_local(r: Reservation) -> dt.datetime:
    return clock.local_dt(r.date, r.s_h, r.s_m)


def end_local(r: Reservation) -> dt.datetime:
    return clock.local_dt(r.date, r.e_h, r.e_m)


def in_window(date: dt.date, today: dt.date) -> bool:
    """노드에 가 있는(또는 갈) 예약인가 — 오늘~+7 (v2 §12)."""
    return today <= date <= today + dt.timedelta(days=RESV_HORIZON_DAYS)


def addr(s: Session, r: Reservation) -> tuple[str, int, str | None]:
    room = s.get(Room, r.room_id)
    b = s.get(Building, room.building_id)
    return b.bld, room.room, b.modem_id


def node_subject(r: Reservation) -> str:
    return r.subject if r.requested_by is None else STUDENT_LABEL


def room_full(s: Session, room_id: int, today: dt.date, exclude_id: int | None = None) -> bool:
    """방의 창(오늘~+7) 안 approved+requested 가 노드 용량(24)에 찼는가. 넘으면 노드가 STORE_FAIL."""
    q = (
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.room_id == room_id,
            Reservation.status.in_(_LIVE),
            Reservation.date >= today,
            Reservation.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS),
        )
    )
    if exclude_id is not None:
        q = q.where(Reservation.id != exclude_id)
    return s.scalar(q) >= NODE_RESV_MAX


def push_set(s: Session, r: Reservation) -> list[int]:
    """RESV_SET 을 호출자 세션으로 enqueue 하고 pushed_at 을 찍는다 — pushed_at 을 바꾸는 두 곳 중 하나."""
    bld, room, _ = addr(s, r)
    ids = api.enqueue_resv_set(
        bld,
        room,
        r.id,
        r.date,
        (r.s_h, r.s_m),
        (r.e_h, r.e_m),
        r.type,
        node_subject(r),
        r.professor,
        session=s,
    )
    r.pushed_at = clock.now_utc()
    return ids


def push_del(
    s: Session,
    r: Reservation,
    now_local: dt.datetime,
    end: tuple[dt.date, int, int] | None = None,
) -> list[int]:
    """노드에 가 있을 수 있는(보낸 적 있고 아직 안 끝난) 예약만 RESV_DEL. 어느 쪽이든 pushed_at 을 비운다.
    `end` = 노드가 가진 항목의 (날짜, 끝 시, 끝 분) — 옮길 때는 옮기기 전 값. 기본은 행의 현재 값."""
    d, e_h, e_m = end or (r.date, r.e_h, r.e_m)
    sent = r.pushed_at is not None
    r.pushed_at = None
    # 지난 날짜·끝난 예약은 노드가 곧 버린다 — 웨이크 낭비
    if not sent or d < now_local.date() or clock.local_dt(d, e_h, e_m) <= now_local:
        return []
    bld, room, _ = addr(s, r)
    return api.enqueue_resv_del(bld, room, r.id, session=s)


def _hit(x, s_min: int, e_min: int) -> bool:
    return x.s_h * 60 + x.s_m < e_min and s_min < x.e_h * 60 + x.e_m


def _blockers(s: Session, room_id: int, date: dt.date, exclude_id: int | None = None) -> list:
    """겹침 판정 대상 — 그 요일 정규 슬롯(type 무관) + 그 날 approved/requested 예약.
    overlaps 와 free_spans 가 같은 목록을 본다: 빈 구간으로 보여준 곳이 겹침 409 가 나지 않게."""
    q = select(Reservation).where(
        Reservation.room_id == room_id,
        Reservation.date == date,
        Reservation.status.in_(_LIVE),
    )
    if exclude_id is not None:
        q = q.where(Reservation.id != exclude_id)
    slots = s.scalars(select(Slot).where(Slot.room_id == room_id, Slot.day == date.isoweekday()))
    return [*slots, *s.scalars(q)]


def overlaps(
    s: Session, room_id: int, date: dt.date, s_min: int, e_min: int, exclude_id: int | None = None
) -> bool:
    """정규 슬롯(그 요일, type 무관)·approved/requested 예약과 1분이라도 겹치면 True.
    시험기간은 슬롯이 있을 때만 의미가 있어 슬롯 겹침에 이미 포함된다."""
    return any(_hit(x, s_min, e_min) for x in _blockers(s, room_id, date, exclude_id))


def free_spans(s: Session, room_id: int, date: dt.date, lo: int) -> list[tuple[int, int]]:
    """[lo, CLOSE_MIN] 안에서 _blockers 의 여집합 (분). 끝점은 5분 격자 안쪽으로 맞추고
    MIN_MIN 보다 짧은 조각은 버린다 — 남은 구간 안의 신청은 겹침·길이·격자 검사를 통과한다."""
    gaps, cur = [], lo
    for a, b in sorted(
        (x.s_h * 60 + x.s_m, x.e_h * 60 + x.e_m) for x in _blockers(s, room_id, date)
    ):
        a, b = min(a, b), max(a, b)  # 0분/뒤집힌 입력도 막힌 구간으로 (merge_busy 와 같은 정신)
        if a > cur:
            gaps.append((cur, a))
        cur = max(cur, b)
    gaps.append((cur, CLOSE_MIN))
    out = []
    for a, b in gaps:
        a, b = -(-a // STEP_MIN) * STEP_MIN, min(b, CLOSE_MIN) // STEP_MIN * STEP_MIN
        if b - a >= MIN_MIN:
            out.append((a, b))
    return out


def free_days(s: Session, room_id: int, now_local: dt.datetime, full: bool) -> list[dict]:
    """예약 화면의 날짜 칩 8개(KST 오늘~+7)와 날마다 신청 가능한 구간 (web A3).
    오늘은 지금 이후만(시작 > 지금). full(= room_full, 호출자가 WeekOut.full 로도 싣는다)이면 전부
    빈 목록 — 신청해도 409 라서."""
    today = now_local.date()
    out = []
    for i in range(RESV_HORIZON_DAYS + 1):  # ponytail: 날마다 쿼리 2개(16개) — 느려지면 범위 조회로
        d = today + dt.timedelta(days=i)
        lo = OPEN_MIN if i else max(OPEN_MIN, now_local.hour * 60 + now_local.minute + 1)
        spans = [] if full else free_spans(s, room_id, d, lo)
        out.append(
            {
                "date": d,
                "spans": [
                    {"from": room_state.fmt_hhmm(a), "to": room_state.fmt_hhmm(b)} for a, b in spans
                ],
            }
        )
    return out


def validate_request(
    s: Session, user: User, room: Room, body: S.StudentResvIn, now_local: dt.datetime
) -> None:
    today = now_local.date()
    if not in_window(body.date, today):
        raise HTTPException(400, f"오늘부터 {RESV_HORIZON_DAYS}일 안에만 신청할 수 있습니다")
    s_min, e_min = body.s_h * 60 + body.s_m, body.e_h * 60 + body.e_m
    if not (MIN_MIN <= e_min - s_min <= MAX_MIN):
        raise HTTPException(400, f"{MIN_MIN}분 이상 {MAX_MIN}분 이하로 신청하세요")
    if clock.local_dt(body.date, body.s_h, body.s_m) <= now_local:
        raise HTTPException(400, "이미 지난 시간입니다")
    # 진행 중 = 아직 시작 안 한 신청 + 아직 안 끝난 승인 (spec "미래 approved"). 날짜만 보면 오늘 끝난
    # 예약이 자정까지, 시작 지난 신청이 04:00 만료까지 한도를 잡는다 (자체 점검 🟡)
    mine = s.scalars(
        select(Reservation).where(
            Reservation.requested_by == user.email,
            Reservation.status.in_(_LIVE),
            Reservation.date >= today,
        )
    )
    active = sum(
        1 for x in mine if (start_local(x) if x.status == "requested" else end_local(x)) > now_local
    )
    if active >= MAX_ACTIVE:
        raise HTTPException(400, f"진행 중인 신청은 {MAX_ACTIVE}건까지입니다")
    if overlaps(s, room.id, body.date, s_min, e_min):
        raise HTTPException(409, "그 시간에는 이미 수업·예약이 있습니다")
    if room_full(s, room.id, today):
        raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다")


def _require(r: Reservation, *states: str) -> None:
    if r.status not in states:
        raise HTTPException(409, f"{r.status} 상태에서는 불가")


def approve(s: Session, r: Reservation, admin_email: str, now_local: dt.datetime) -> list[int]:
    _require(r, "requested")
    if start_local(r) <= now_local:
        raise HTTPException(409, "이미 시작 시각이 지난 신청입니다")
    if overlaps(s, r.room_id, r.date, r.s_h * 60 + r.s_m, r.e_h * 60 + r.e_m, exclude_id=r.id):
        raise HTTPException(409, "그 시간에 다른 예약·수업이 생겼습니다")
    if room_full(s, r.room_id, now_local.date(), exclude_id=r.id):
        raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)")
    r.status, r.decided_at, r.decided_by = "approved", clock.to_utc(now_local), admin_email
    if not in_window(r.date, now_local.date()):
        return []  # 창 밖 — pushed_at NULL 로 남아 창에 들어오는 날 일일 작업이 승격 (S10 §2.5)
    return push_set(s, r)


def reject(
    s: Session, r: Reservation, admin_email: str, reason: str, now_local: dt.datetime
) -> None:
    _require(r, "requested")
    r.status, r.decided_at, r.decided_by = "rejected", clock.to_utc(now_local), admin_email
    r.reject_reason = reason


def withdraw(s: Session, r: Reservation) -> None:
    """학생이 결정 전 신청을 거둔다 — 행을 지워 u16 id 를 바로 돌려준다 (신청·철회 반복으로 id 소진 방지)."""
    _require(r, "requested")
    s.delete(r)


def cancel(s: Session, r: Reservation, *, by_admin: bool, now_local: dt.datetime) -> list[int]:
    """approved → cancelled. 학생은 시작 전만. 노드로 보낸 적 있는 예약만 RESV_DEL(push_del)."""
    _require(r, "approved")
    if not by_admin and start_local(r) <= now_local:
        raise HTTPException(409, "시작된 예약은 취소할 수 없습니다")
    r.status, r.cancelled_at = "cancelled", clock.to_utc(now_local)
    return push_del(s, r, now_local)


def checkin(s: Session, r: Reservation, now_local: dt.datetime) -> None:
    _require(r, "approved")
    if r.checked_in_at is not None:
        raise HTTPException(409, "이미 체크인했습니다")
    st = start_local(r)
    lo, hi = st - dt.timedelta(minutes=CHECKIN_BEFORE), st + dt.timedelta(minutes=CHECKIN_AFTER)
    if not (lo <= now_local <= hi):
        raise HTTPException(
            409, f"체크인은 시작 {CHECKIN_BEFORE}분 전부터 {CHECKIN_AFTER}분 후까지입니다"
        )
    r.checked_in_at = clock.to_utc(now_local)
