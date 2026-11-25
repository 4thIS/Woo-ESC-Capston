"""미리보기·적용 (spec §5.2·§5.4). 둘 다 같은 run_ops(= app.domain.ops 의 쓰기 함수)를 _ID_LOCK 안에서 돌린다.
미리보기 = 실행 → 읽기 → rollback, 적용 = 저장된 확정 변경 목록 실행 → 커밋 → notify.
요청 세션(_DB)이 아니라 새 세션을 연다 — 쓰고 되돌리는 일을 요청 세션과 섞지 않는다."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets

import pydantic
import sqlalchemy.exc
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import schemas as S
from app.assistant import changes, manifest
from app.assistant import schemas as AS
from app.assistant.models import AssistantChange, AssistantConversation, AssistantPreview
from app.auth import scope
from app.auth.scope import Scope
from app.domain import admin, clock, reserve
from app.domain import ops as dops
from app.domain import router as R
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service import api

PREVIEW_TTL = dt.timedelta(minutes=10)
_OP_ERRORS = (
    HTTPException,
    api.ValidationError,
    api.NotFound,
    pydantic.ValidationError,
    sqlalchemy.exc.IntegrityError,
)
_SLOT_F = ("e_h", "e_m", "type", "subject", "professor")
_RESV_F = ("date", "s_h", "s_m", "e_h", "e_m", "type", "subject", "professor", "status")
_EXAM_F = ("date_start", "date_end")


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _message(e: Exception) -> str:
    if isinstance(e, HTTPException):
        return str(e.detail)
    if isinstance(e, pydantic.ValidationError):
        return f"입력값이 규칙에 맞지 않습니다: {e.errors()[0].get('msg', '')}"
    if isinstance(e, sqlalchemy.exc.IntegrityError):
        return "저장할 수 없는 변경입니다(제약 위반)."
    return str(e)


def run_ops(
    s: Session, sc: Scope, ops_: list[dict], actor: str, now_local: dt.datetime
) -> tuple[list[int], set[str]]:
    """확정 변경 목록 실행 — 커밋하지 않는다. 호출자가 _ID_LOCK 을 잡는다."""
    ids: list[int] = []
    modems: set[str] = set()
    for op in ops_:
        room = scope.get_scoped(s, Room, op["room_id"], sc)  # 범위 재확인 — 밖이면 404
        bld, num, mid = dops.room_addr(s, room.id)
        if mid:
            modems.add(mid)
        k = op["op"]
        if k == "slot.put":
            ids += dops.put_slot(s, room.id, bld, num, S.SlotIn(**op["slot"]))
        elif k == "slot.del":
            ids += dops.delete_slot(s, room.id, bld, num, op["day"], op["s_h"], op["s_m"])
        elif k == "resv.put":
            body = S.ResvIn(**op["resv"])
            if op["id"] is None:
                rid, obj = R._free_id(s, Reservation), None
            else:
                rid, obj = op["id"], R._existing_same_room(s, Reservation, op["id"], room.id)
            ids += dops.write_resv(s, room.id, body, rid, obj, now_local)
        elif k == "resv.del":
            ids += dops.delete_resv(s, room.id, op["id"], now_local) or []
        elif k == "exam.put":
            body = S.ExamIn(**op["exam"])
            if op["id"] is None:
                eid, obj = R._free_id(s, ExamPeriod), None
            else:
                eid, obj = op["id"], R._existing_same_room(s, ExamPeriod, op["id"], room.id)
            ids += dops.write_exam(s, room.id, bld, num, body, eid, obj)
        elif k == "exam.del":
            ids += dops.delete_exam(s, room.id, bld, num, op["id"])
        elif k in ("request.approve", "request.reject"):
            r = s.get(Reservation, op["id"])
            if r is None or r.room_id != room.id:
                raise HTTPException(409, "신청을 찾지 못했습니다 — 이미 처리됐을 수 있습니다")
            if k == "request.approve":
                ids += reserve.approve(s, r, actor, now_local)
            else:
                reserve.reject(s, r, actor, op["reason"], now_local)
        else:
            raise ValueError(f"모르는 op {k}")
        s.flush()  # 다음 채번·용량 검사가 방금 쓴 행을 보게
    return ids, modems


def fingerprint(s: Session, room_ids: list[int]) -> str:
    """미리보기 뒤 같은 방들이 바뀌었는지 — 정규 시간표·예약·시험기간 전부 (pushed_at 은 빼고)."""
    h = hashlib.sha256()
    for rid in sorted(room_ids):
        q = select(Slot).where(Slot.room_id == rid).order_by(Slot.day, Slot.s_h, Slot.s_m)
        for x in s.scalars(q):
            h.update(
                repr(
                    (
                        "s",
                        rid,
                        x.day,
                        x.s_h,
                        x.s_m,
                        x.e_h,
                        x.e_m,
                        x.type,
                        x.subject,
                        x.professor,
                        x.source,
                    )
                ).encode()
            )
        q = select(Reservation).where(Reservation.room_id == rid).order_by(Reservation.id)
        for x in s.scalars(q):
            h.update(
                repr(
                    (
                        "r",
                        x.id,
                        x.date.isoformat(),
                        x.s_h,
                        x.s_m,
                        x.e_h,
                        x.e_m,
                        x.type,
                        x.subject,
                        x.professor,
                        x.status,
                    )
                ).encode()
            )
        q = select(ExamPeriod).where(ExamPeriod.room_id == rid).order_by(ExamPeriod.id)
        for x in s.scalars(q):
            h.update(repr(("e", x.id, x.date_start.isoformat(), x.date_end.isoformat())).encode())
    return h.hexdigest()


def week_data(s: Session, room_id: int, wk: str | None) -> dict:
    """부록 WeekData — 정규 시간표 전부 + (주가 있으면) 그 주 승인·신청 예약과 겹치는 시험기간. JSON 모드."""
    q = select(Slot).where(Slot.room_id == room_id).order_by(Slot.day, Slot.s_h, Slot.s_m)
    slots = [S.SlotWithRoom.model_validate(x).model_dump(mode="json") for x in s.scalars(q)]
    if wk is None:
        return {"slots": slots, "reservations": [], "exams": []}
    mon = dt.date.fromisoformat(wk)
    sun = mon + dt.timedelta(days=6)
    rows = admin.resv_with_room_rows(
        s,
        select(Reservation)
        .where(
            Reservation.room_id == room_id,
            Reservation.status.in_(("approved", "requested")),
            Reservation.date.between(mon, sun),
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id),
    )
    q = (
        select(ExamPeriod)
        .where(
            ExamPeriod.room_id == room_id, ExamPeriod.date_start <= sun, ExamPeriod.date_end >= mon
        )
        .order_by(ExamPeriod.date_start)
    )
    return {
        "slots": slots,
        "reservations": [S.ResvWithRoom.model_validate(x).model_dump(mode="json") for x in rows],
        "exams": [S.ExamWithRoom.model_validate(x).model_dump(mode="json") for x in s.scalars(q)],
    }


def _keyed(w: dict) -> dict[str, tuple[str, dict, tuple[str, ...]]]:
    out = {}
    for x in w["slots"]:
        out[f"d{x['day']}-{x['s_h']:02d}{x['s_m']:02d}"] = ("slot", x, _SLOT_F)
    for x in w["reservations"]:
        out[f"r{x['id']}"] = ("resv", x, _RESV_F)
    for x in w["exams"]:
        out[f"e{x['id']}"] = ("exam", x, _EXAM_F)
    return out


def marks(before: dict, after: dict) -> list[dict]:
    """부록 changes[] — key 규칙 d{day}-{HHMM} · r{id} · e{id}."""
    b, a = _keyed(before), _keyed(after)
    out = []
    for k in sorted(b.keys() | a.keys()):
        if k not in a:
            out.append({"entity": b[k][0], "key": k, "op": "remove", "fields": []})
        elif k not in b:
            out.append({"entity": a[k][0], "key": k, "op": "add", "fields": []})
        else:
            ent, x, fs = a[k]
            changed = [f for f in fs if x[f] != b[k][1][f]]
            if changed:
                out.append({"entity": ent, "key": k, "op": "change", "fields": changed})
    return out


def _draft_rooms(draft: dict) -> set[int]:
    st, tg = draft["set"], draft["target"]
    ids = set(st.get("rooms", [])) | set(tg.get("rooms", []))
    ids |= {e["room_id"] for e in st.get("entries", [])}
    return ids


def _in_scope(s: Session, sc: Scope, ids: set[int]) -> bool:
    """모든 방이 관리자 범위 안인가 — 하나라도 밖이면 False. 데이터는 읽지 않고 방 번호만 본다."""
    if not ids:
        return True
    q = (
        select(Room.id)
        .join(Building, Room.building_id == Building.id)
        .where(scope.building_clause(sc), Room.id.in_(ids))
    )
    return set(s.scalars(q)) == ids


def _earliest_start(ops_: list[dict], fallback: dt.datetime) -> dt.datetime:
    """쓰는 일정(resv.put) 중 가장 이른 시작(UTC) — 시작 뒤에는 적용할 수 없다."""
    best = fallback
    for op in ops_:
        if op["op"] == "resv.put":
            r = op["resv"]
            start = clock.to_utc(
                clock.local_dt(dt.date.fromisoformat(r["date"]), r["s_h"], r["s_m"])
            )
            best = min(best, start)
    return best


def _store(Session: sessionmaker, sc: Scope, conv_id: str, draft: dict, now_utc, **cols) -> str:
    pid = "p_" + secrets.token_hex(8)
    with Session() as s, s.begin():
        s.add(
            AssistantPreview(
                id=pid,
                conversation_id=conv_id,
                user_email=sc.email,
                draft=_j(draft),
                created_at=now_utc,
                **cols,
            )
        )
    return pid


def make_preview(
    Session: sessionmaker, sc: Scope, conv_id: str, draft: dict, now_local: dt.datetime
) -> dict:
    now_utc = clock.to_utc(now_local)
    with Session() as s:  # 범위 먼저 — 밖이면 어떤 데이터도 읽지 않는다
        in_scope = _in_scope(s, sc, _draft_rooms(draft))
    if not in_scope:
        blockers = ["권한 밖 강의실이 있습니다"]
        expires = now_utc + PREVIEW_TTL
        pid = _store(
            Session,
            sc,
            conv_id,
            draft,
            now_utc,
            ops="[]",
            room_ids="[]",
            fingerprint="",
            blockers=_j(blockers),
            summary="[]",
            expires_at=expires,
        )
        return {
            "preview_id": pid,
            "expires_at": expires.replace(tzinfo=dt.UTC),
            "summary": [],
            "blockers": blockers,
            "warnings": [],
            "notices": [],
            "rooms": [],
        }
    with R._ID_LOCK, Session() as s:
        try:
            built = changes.plan(s, sc, draft, now_local)
            blockers = list(built.blockers)
            fp = fingerprint(s, built.room_ids)
            keys = [(rid, wk) for rid in built.room_ids for wk in built.weeks[rid]]
            before = {k: week_data(s, *k) for k in keys}
            if len(built.ops) > changes.OPS_MAX:  # 너무 많으면 돌려 보지 않는다(막음이 이미 있다)
                after = before
            else:
                try:
                    run_ops(s, sc, built.ops, sc.email, now_local)
                    after = {k: week_data(s, *k) for k in keys}
                except _OP_ERRORS as e:
                    blockers.append(_message(e))
                    after = before
            bld_of = dict(
                s.execute(
                    select(Room.id, Room.building_id).where(Room.id.in_(built.room_ids))
                ).all()
            )
        finally:
            s.rollback()  # 미리보기는 아무것도 남기지 않는다 — 도메인 행·outbox·버전 모두
    rooms_out = []
    notices = list(built.notices)
    if not blockers and not any(
        marks(before[k], after[k]) for k in keys
    ):  # 실행해 보니 아무것도 안 바뀐다 — 변경 기록을 남길 이유가 없다
        blockers.append(changes.NOOP)
    for rid in built.room_ids:
        seen = set()
        for wk in built.weeks[rid]:  # 센 값은 영향받는 주 전부
            seen |= {(m["key"], m["op"]) for m in marks(before[(rid, wk)], after[(rid, wk)])}
        drawn = built.drawn(rid)
        if len(built.weeks[rid]) > len(drawn):
            notices.append(
                f"{built.labels[rid]}: {len(built.weeks[rid])}주 중 앞 {len(drawn)}주만 그렸습니다"
            )
        rooms_out.append(
            {
                "room_id": rid,
                "building_id": bld_of[rid],
                "label": built.labels[rid],
                "added": sum(op == "add" for _, op in seen),
                "removed": sum(op == "remove" for _, op in seen),
                "changed": sum(op == "change" for _, op in seen),
                "weeks": [
                    {
                        "week_start": wk,
                        "before": before[(rid, wk)],
                        "after": after[(rid, wk)],
                        "changes": marks(before[(rid, wk)], after[(rid, wk)]),
                    }
                    for wk in drawn
                ],
            }
        )
    expires = now_utc + PREVIEW_TTL
    first = _earliest_start(built.ops, expires)
    if first > now_utc:  # 이미 시작한 일정은 막음(blocker)이 따로 잡는다
        expires = first
    pid = _store(
        Session,
        sc,
        conv_id,
        draft,
        now_utc,
        ops=_j(built.ops),
        room_ids=_j(built.room_ids),
        fingerprint=fp,
        blockers=_j(blockers),
        summary=_j(built.summary),
        expires_at=expires,
    )
    return {
        "preview_id": pid,
        "expires_at": expires.replace(tzinfo=dt.UTC),
        "summary": built.summary,
        "blockers": blockers,
        "warnings": built.warnings,
        "notices": notices,
        "rooms": rooms_out,
    }


def apply_preview(
    Session: sessionmaker, sc: Scope, preview_id: str, now_local: dt.datetime
) -> tuple[int, dict]:
    now_utc = clock.to_utc(now_local)
    stale: tuple[str, dict] | None = None
    with R._ID_LOCK, Session() as s:
        p = s.get(AssistantPreview, preview_id)
        if p is None or p.user_email != sc.email:
            return 404, {"detail": "미리보기 없음"}
        room_ids = json.loads(p.room_ids)
        if not _in_scope(
            s, sc, set(room_ids)
        ):  # 범위를 잃었으면 없는 것과 같다 — 새 미리보기도 만들지 않는다
            return 404, {"detail": "미리보기 없음"}
        if p.applied_at is not None or p.expires_at <= now_utc:
            return 410, {"detail": "expired"}
        blockers = json.loads(p.blockers)
        if blockers:
            return 422, {"detail": "blocked", "blockers": blockers}
        if fingerprint(s, room_ids) != p.fingerprint:
            stale = (p.conversation_id, json.loads(p.draft))
            p.expires_at = now_utc  # 옛 미리보기는 더 못 쓴다
            s.commit()
        else:
            try:
                ids, modems = run_ops(s, sc, json.loads(p.ops), sc.email, now_local)
            except _OP_ERRORS as e:
                s.rollback()  # 한 트랜잭션 — 하나라도 실패하면 아무것도 바뀌지 않는다
                return 422, {"detail": "blocked", "blockers": [_message(e)]}
            draft = json.loads(p.draft)
            bids = sorted(set(s.scalars(select(Room.building_id).where(Room.id.in_(room_ids)))))
            ch = AssistantChange(
                preview_id=p.id,
                user_email=sc.email,
                school_id=sc.school_id,
                building_ids=_j(bids),
                utterance=" / ".join(draft["utterances"]),
                ops=p.ops,
                summary=p.summary,
                outbox_ids=_j(ids),
                model_rev=manifest.current_revision(),
                applied_at=now_utc,
            )
            s.add(ch)
            p.applied_at = now_utc
            conv = s.get(AssistantConversation, p.conversation_id)
            if conv is not None:  # 적용하면 그 대화는 끝 — 같은 대화로 또 미리보기·적용하지 못하게
                conv.state, conv.updated_at, conv.closed_at = "null", now_utc, now_utc
            s.flush()
            change_id = ch.id
            s.commit()
    if stale is not None:  # 락 밖에서 — make_preview 가 락을 다시 잡는다(비재진입)
        return 409, {
            "detail": "stale",
            "preview": AS.PreviewOut(
                **make_preview(Session, sc, stale[0], stale[1], now_local)
            ).model_dump(mode="json"),
        }
    for m in modems:
        api.notify(m)
    return 200, {"change_id": change_id, "outbox_ids": ids}
