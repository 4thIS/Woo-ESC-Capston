"""04:00 일일 작업 (S10 §2.5): 만료 → 승격 → 실패 재동기 → 정리 → 기록. 단계별 트랜잭션, 오류는 계속."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import threading

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import EmailToken
from app.domain import clock, reserve
from app.domain.models import JobRun, Reservation
from app.domain.router import _ID_LOCK
from app.domain.topology import RESV_HORIZON_DAYS
from app.lora_service import api
from app.lora_service.api import KIND_OF
from app.lora_service.models import Outbox

log = logging.getLogger(__name__)
KEEP_DAYS = 90
DECIDED_KEEP_DAYS = 7  # 거절·만료 신청은 1주 뒤 지운다 — u16 id 를 오래 잡지 않게
TOKEN_KEEP_DAYS = 7
RESYNC_WINDOW_H = 24
FILE_KINDS = {1: "schedule", 2: "resv", 3: "exam"}  # FILE payload.kind → room_versions.kind
# 자동(daily_loop)·수동(POST /jobs/daily) 실행이 겹치지 않게 — 단일 워커 전제
_RUN_LOCK = threading.Lock()


def _kind_of(o: Outbox) -> str | None:
    if o.type == "FILE":  # KIND_OF 엔 FILE 이 없다 — payload.kind 로
        try:
            return FILE_KINDS.get(json.loads(o.payload).get("kind"))
        except ValueError:
            return None
    return KIND_OF.get(o.type)


def _expire(s: Session, now_local: dt.datetime) -> int:
    n = 0
    for r in s.scalars(select(Reservation).where(Reservation.status == "requested")):
        if reserve.start_local(r) < now_local:
            r.status = "expired"
            n += 1
    return n


def _pushed_in_window(s: Session, room_id: int, today: dt.date) -> int:
    return s.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.room_id == room_id,
            Reservation.pushed_at.is_not(None),
            Reservation.date >= today,
            Reservation.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS),
        )
    )


def _promote(Session: sessionmaker, now_local: dt.datetime, errors: list[str]) -> int:
    """창 안(오늘~오늘+7)인데 아직 노드로 안 보낸(pushed_at IS NULL) 승인 예약을 RESV_SET.
    서버가 하루를 놓쳐도 다음 실행이 따라잡고, outbox 이력이 아니라 pushed_at 으로 판단해 id 재사용에 속지 않는다.
    예약마다 자기 트랜잭션 — pysqlite 기본 설정에선 SAVEPOINT 가 안 돼 한 세션에서 부분 롤백을 못 한다.
    실패분은 pushed_at NULL 로 남아 다음 날 재시도."""
    today = now_local.date()
    with Session() as s:
        ids = s.scalars(
            select(Reservation.id)
            .where(
                Reservation.status == "approved",
                Reservation.pushed_at.is_(None),
                Reservation.date >= today,
                Reservation.date <= today + dt.timedelta(days=RESV_HORIZON_DAYS),
            )
            .order_by(Reservation.date, Reservation.id)
        ).all()
    n = 0
    for rid in ids:
        try:
            # 그 사이 바뀐 행을 옛 값으로 보내지 않게 — 락 안에서 다시 읽는다
            with Session() as s, _ID_LOCK:
                r = s.get(Reservation, rid)
                if r is None or r.status != "approved" or r.pushed_at is not None:
                    continue  # 그 사이 취소·삭제·전송됨
                if not reserve.in_window(r.date, today) or reserve.end_local(r) <= now_local:
                    continue  # 날짜가 창 밖으로 옮겨졌거나 오늘 이미 끝남 — 웨이크 낭비
                if _pushed_in_window(s, r.room_id, today) >= reserve.NODE_RESV_MAX:
                    errors.append(
                        f"promoted: resv {rid}: 방 예약이 노드 용량({reserve.NODE_RESV_MAX})에 참"
                    )
                    continue
                mid = reserve.addr(s, r)[2]
                reserve.push_set(s, r)
                s.commit()
            api.notify(mid)  # 커밋 뒤 (S2c)
            n += 1
        except Exception as e:
            log.exception("승격 실패 resv %s", rid)
            errors.append(f"promoted: resv {rid}: {e}")
    return n


def _resync_failed(s: Session, now_utc: dt.datetime, errors: list[str]) -> list[list]:
    """지난 24 h 실패한 (bld, room, unit) 마다 실패한 kind 들로 FILE 재동기 1회.
    관리자 취소분·CMD·SET_ROOM·TIME 제외. 방 하나가 실패해도 나머지는 계속한다."""
    since = now_utc - dt.timedelta(hours=RESYNC_WINDOW_H)
    kinds: dict[tuple[str, int, int], set[str]] = {}
    for o in s.scalars(select(Outbox).where(Outbox.state == "failed", Outbox.finished_at >= since)):
        if o.last_error == "cancelled":
            continue
        kind = _kind_of(o)
        if kind in FILE_KINDS.values():
            kinds.setdefault((o.bld, o.room, o.unit), set()).add(kind)
    out = []
    for (bld, room, unit), ks in sorted(kinds.items()):
        try:
            # 자기 세션 — RecordProvider 가 커밋된 DB 를 읽는다
            api.enqueue_full_sync(bld, room, tuple(sorted(ks)), unit=unit)
            out.append([bld, room, unit, sorted(ks)])
        except Exception as e:
            log.exception("재동기 실패 %s%s/%s", bld, room, unit)
            errors.append(f"resynced: {bld}{room}/{unit}: {e}")
    return out


def _prune(s: Session, now_utc: dt.datetime, now_local: dt.datetime) -> dict:
    today = now_local.date()
    old = Reservation.date < today - dt.timedelta(days=KEEP_DAYS)
    decided = Reservation.status.in_(("rejected", "expired")) & (
        Reservation.date < today - dt.timedelta(days=DECIDED_KEEP_DAYS)
    )
    job_cut = now_utc - dt.timedelta(days=KEEP_DAYS)
    token_cut = now_utc - dt.timedelta(days=TOKEN_KEEP_DAYS)
    return {
        "reservations": s.execute(delete(Reservation).where(old | decided)).rowcount,
        "job_runs": s.execute(delete(JobRun).where(JobRun.ran_at < job_cut)).rowcount,
        "email_tokens": s.execute(
            delete(EmailToken).where(EmailToken.expires_at < token_cut)
        ).rowcount,
    }


def run_daily(Session: sessionmaker, now_utc: dt.datetime | None = None) -> dict:
    with _RUN_LOCK:
        return _run_daily(Session, now_utc)


def _run_daily(Session: sessionmaker, now_utc: dt.datetime | None) -> dict:
    now_utc = now_utc or clock.now_utc()
    now_local = clock.to_local(now_utc)
    res: dict = {"expired": 0, "promoted": 0, "resynced": [], "pruned": {}, "errors": []}

    def step(name, fn):
        try:
            with Session() as s, s.begin():
                res[name] = fn(s)
        except Exception as e:  # 한 단계 실패가 나머지를 막지 않는다
            log.exception("daily %s 실패", name)
            res["errors"].append(f"{name}: {e}")

    step("expired", lambda s: _expire(s, now_local))
    step("promoted", lambda s: _promote(Session, now_local, res["errors"]))  # 예약마다 자기 세션
    step("resynced", lambda s: _resync_failed(s, now_utc, res["errors"]))
    step("pruned", lambda s: _prune(s, now_utc, now_local))
    with Session() as s, s.begin():
        s.add(JobRun(name="daily", ran_at=now_utc, result=json.dumps(res, ensure_ascii=False)))
    return res


def already_ran_today(s: Session, now_local: dt.datetime) -> bool:
    """오늘 04:00(KST) 이후 실행 기록이 있는가 — 그 전의 수동 실행은 세지 않는다."""
    start_utc = clock.to_utc(dt.datetime.combine(now_local.date(), dt.time(clock.DAILY_HOUR_LOCAL)))
    q = select(JobRun.id).where(JobRun.name == "daily", JobRun.ran_at >= start_utc).limit(1)
    return s.scalar(q) is not None


def tick(Session: sessionmaker) -> bool:
    """04:00(KST) 이후이고 오늘 아직 안 돌았으면 실행. 돌았으면 True."""
    now_utc = clock.now_utc()
    now_local = clock.to_local(now_utc)
    if now_local.hour < clock.DAILY_HOUR_LOCAL:
        return False
    with Session() as s:
        if already_ran_today(s, now_local):
            return False
    run_daily(Session, now_utc)
    return True


async def daily_loop(Session: sessionmaker, interval_s: float = 60.0) -> None:
    while True:
        # sleep 먼저 — 기동 직후(테스트 포함) clock 이 monkeypatch 되기 전 실제 시각으로 돌지 않게
        await asyncio.sleep(interval_s)
        try:
            await asyncio.to_thread(tick, Session)
        except Exception:
            log.exception("daily tick 실패")
