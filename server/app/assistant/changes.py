"""초안(draft) → 대상 찾기 · 확정 변경 목록 · 요약 · 경고 (spec §5). DB 는 읽기만 — 쓰기는 preview.run_ops.

초안 = dialog.advance 가 만든 해석 결과 {"intent", "target": R, "set": R, "pick", "utterances"}.
R 의 키는 plan 01 Task 10 Interfaces 표 그대로."""

from __future__ import annotations

import datetime as dt

from assistant_proto import TYPE_LABELS
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import scope
from app.auth.models import User
from app.auth.scope import Scope
from app.domain import clock, reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot

WD = "월화수목금토일"
TYPE = dict(enumerate(TYPE_LABELS, start=1))


def d_(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


def hm(x: str) -> tuple[int, int]:
    h, m = x.split(":")
    return int(h), int(m)


def md(d: dt.date) -> str:
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def span(sh: int, sm: int, eh: int, em: int) -> str:
    return f"{sh:02d}:{sm:02d}–{eh:02d}:{em:02d}"


def week_of(d: dt.date) -> str:
    return clock.week_start(d).isoformat()


def room_labels(s: Session, ids) -> dict[int, str]:
    q = (
        select(Room.id, Building.name, Room.room)
        .join(Building, Room.building_id == Building.id)
        .where(Room.id.in_(list(ids)))
    )
    return {rid: f"{name} {num}" for rid, name, num in s.execute(q).all()}


def _hit(x, s_min: int, e_min: int) -> bool:
    return x.s_h * 60 + x.s_m < e_min and s_min < x.e_h * 60 + x.e_m


def _squash(x: str) -> str:
    return "".join(x.split())


def same_subject(want: str, have: str | None) -> bool:
    """공백을 뺀 이름이 같거나, 한쪽이 다른 쪽을 포함하고 짧은 쪽이 2자 이상."""
    a, b = _squash(want), _squash(have or "")
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 2 and (a in b or b in a)


def _match(x, tg: dict) -> bool:
    """시작 시각·유형·이름(서로 포함)이 맞는가 — 대상 찾기 공용."""
    if "time" in tg and (x.s_h, x.s_m) != hm(tg["time"][0]):
        return False
    if "type" in tg and x.type != tg["type"]:
        return False
    return not ("subject" in tg and not same_subject(tg["subject"], x.subject))


def fill_from_slots(
    s: Session, draft: dict, now_local: dt.datetime | None = None
) -> tuple[str, str] | None:
    """휴강 — 그날 정규 수업에서 시각·이름을 찾아 set.entries 로 펼친다 (수업마다 휴강 하나).
    시각을 다 말했는데 그 시각 수업이 없으면 말한 시각 그대로. 아무것도 못 찾으면 (묻는 칸, 문구)."""
    st = draft["set"]
    if st.get("type") != 3:
        return None
    t = st.get("time")
    if now_local is not None:  # 지난 날짜는 펼치지 않는다
        st["dates"] = [x for x in st["dates"] if d_(x) >= now_local.date()]
        if not st["dates"]:
            return ("when", "이미 지난 날짜입니다. 날짜를 다시 알려 주세요.")
    entries: list[dict] = []
    for rid in st["rooms"]:
        for iso in st["dates"]:
            day = d_(iso).isoweekday()
            q = (
                select(Slot)
                .where(Slot.room_id == rid, Slot.day == day, Slot.type != 4)
                .order_by(Slot.s_h, Slot.s_m)
            )
            for x in s.scalars(q):
                if t is not None:
                    sh, sm = hm(t[0])
                    if t[1] is None:
                        hit = (x.s_h, x.s_m) == (sh, sm)
                    else:
                        eh, em = hm(t[1])
                        hit = _hit(x, sh * 60 + sm, eh * 60 + em)
                elif "subject" in st:
                    hit = same_subject(st["subject"], x.subject)
                else:
                    hit = True
                if hit:
                    entries.append(
                        {
                            "room_id": rid,
                            "date": iso,
                            "start": f"{x.s_h:02d}:{x.s_m:02d}",
                            "end": f"{x.e_h:02d}:{x.e_m:02d}",
                            "subject": x.subject,
                            "professor": x.professor,
                        }
                    )
    if not entries and t is not None and t[1] is not None:
        entries = [
            {
                "room_id": rid,
                "date": iso,
                "start": t[0],
                "end": t[1],
                "subject": st.get("subject", "휴강"),
                "professor": st.get("professor", ""),
            }
            for rid in st["rooms"]
            for iso in st["dates"]
        ]
    if not entries:
        return (
            "time",
            "그날 휴강할 정규 수업을 찾지 못했습니다. 몇 시부터 몇 시까지인지 알려 주세요.",
        )
    st["entries"] = entries
    return None


def _event_cands(s: Session, rid: int, tg: dict, now_local: dt.datetime) -> list[dict]:
    q = (
        select(Reservation)
        .where(
            Reservation.room_id == rid,
            Reservation.status == "approved",
            Reservation.date.in_([d_(x) for x in tg["dates"]]),
            Reservation.date >= now_local.date(),  # 지난 일정은 대상이 아니다
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id)
    )
    return [
        {
            "key": f"r{r.id}",
            "id": r.id,
            "date": r.date.isoformat(),
            "label": (
                f"{md(r.date)} {span(r.s_h, r.s_m, r.e_h, r.e_m)} {TYPE[r.type]} {r.subject}".rstrip()
                + (" (학생 예약)" if r.requested_by else "")
            ),
        }
        for r in s.scalars(q)
        if _match(r, tg)
    ]


def _class_cands(s: Session, rid: int, tg: dict, now_local: dt.datetime) -> list[dict]:
    q = (
        select(Slot)
        .where(Slot.room_id == rid, Slot.day.in_(tg["weekdays"]), Slot.type != 4)
        .order_by(Slot.day, Slot.s_h, Slot.s_m)
    )
    return [
        {
            "key": f"d{x.day}-{x.s_h:02d}{x.s_m:02d}",
            "day": x.day,
            "s_h": x.s_h,
            "s_m": x.s_m,
            "label": f"{WD[x.day - 1]} {span(x.s_h, x.s_m, x.e_h, x.e_m)} {x.subject}",
        }
        for x in s.scalars(q)
        if _match(x, tg)
    ]


def _exam_cands(s: Session, rid: int, tg: dict, now_local: dt.datetime) -> list[dict]:
    q = select(ExamPeriod).where(ExamPeriod.room_id == rid).order_by(ExamPeriod.date_start)
    if "range" in tg:
        a, z = d_(tg["range"][0]), d_(tg["range"][1])
        q = q.where(ExamPeriod.date_start <= z, ExamPeriod.date_end >= a)
    return [
        {
            "key": f"e{x.id}",
            "id": x.id,
            "start": x.date_start.isoformat(),
            "end": x.date_end.isoformat(),
            "label": f"{md(x.date_start)}~{md(x.date_end)}",
        }
        for x in s.scalars(q)
    ]


def _who(u: User | None, expr: str) -> bool:
    return u is not None and (
        expr in u.name or expr == (u.student_no or "") or expr == u.email.split("@")[0]
    )


def _request_cands(s: Session, sc: Scope, tg: dict, now_local: dt.datetime) -> list[dict]:
    q = (
        select(Reservation, Room, Building)
        .join(Room, Room.id == Reservation.room_id)
        .join(Building, Building.id == Room.building_id)
        .where(
            scope.building_clause(sc),
            Reservation.status == "requested",
            reserve.not_started(now_local),  # 시작 지난 신청은 승인 불가(409) — 목록에서도 뺀다
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id)
    )
    if "rooms" in tg:
        q = q.where(Room.id.in_(tg["rooms"]))
    if "dates" in tg:
        q = q.where(Reservation.date.in_([d_(x) for x in tg["dates"]]))
    out = []
    for r, room, b in s.execute(q).all():
        if not _match(r, {k: v for k, v in tg.items() if k in ("time", "type")}):
            continue
        u = s.get(User, r.requested_by) if r.requested_by else None
        if "requester" in tg and not _who(u, tg["requester"]):
            continue
        who = u.name if u else "-"
        out.append(
            {
                "key": f"q{r.id}",
                "id": r.id,
                "room_id": room.id,
                "date": r.date.isoformat(),
                "label": f'{b.name} {room.room} {md(r.date)} {span(r.s_h, r.s_m, r.e_h, r.e_m)} {who} "{r.subject}"',
            }
        )
    return out


def find_candidates(
    s: Session, sc: Scope, draft: dict, now_local: dt.datetime
) -> dict[int, list[dict]]:
    """수정·삭제·승인 대상 후보 — 방별. 신청(request.*)은 방을 가로질러 방 키 0 하나에 모은다."""
    grp, tg = draft["intent"].split(".")[0], draft["target"]
    if grp == "request":
        return {0: _request_cands(s, sc, tg, now_local)}
    fn = {"event": _event_cands, "class": _class_cands, "exam": _exam_cands}[grp]
    return {rid: fn(s, rid, tg, now_local) for rid in tg["rooms"]}


def chosen(cands: dict[int, list[dict]], picks: dict[str, str]) -> dict[int, dict]:
    """방마다 대상 하나 — 후보가 하나면 그것, 여럿이면 고른 것. 0개인 방은 빠진다."""
    out = {}
    for rid, lst in cands.items():
        if len(lst) == 1:
            out[rid] = lst[0]
        elif len(lst) > 1:
            hit = [c for c in lst if c["key"] == picks.get(str(rid))]
            if hit:
                out[rid] = hit[0]
    return out


def not_found_message(intent: str) -> str:
    return {
        "event": "말씀하신 일정을 찾지 못했습니다. 날짜·시각·이름을 다시 알려 주세요.",
        "class": "말씀하신 정규 수업을 찾지 못했습니다. 요일·시각·과목을 다시 알려 주세요.",
        "exam": "시험기간을 찾지 못했습니다.",
        "request": "대기 중인 신청을 찾지 못했습니다.",
    }[intent.split(".")[0]]
