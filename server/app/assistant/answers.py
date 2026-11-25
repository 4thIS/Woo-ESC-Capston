"""조회 답 (ask.*, spec §4) — 확인 화면 없이 표 하나. 기존 집계 함수를 그대로 쓴다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.changes import TYPE, d_, hm, md, room_labels, span
from app.auth.scope import Scope, building_clause
from app.domain import admin, analytics, clock, reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot

SCHEDULE_DAYS_MAX = 14
_WARN = {
    "unseen": "응답 없음",
    "low_batt": "배터리 낮음",
    "resync": "재동기 필요",
    "clock_stale": "시계 오래됨",
}


def _min(hhmm: str) -> int:
    h, m = hm(hhmm)
    return h * 60 + m


def answer(s: Session, sc: Scope, draft: dict, now_local: dt.datetime) -> dict:
    fn = {
        "ask.free_rooms": _free,
        "ask.schedule": _schedule,
        "ask.requests": _requests,
        "ask.node": _node,
    }
    return fn[draft["intent"]](s, sc, draft["target"], now_local)


def _free(s, sc, tg, now_local) -> dict:
    d = d_(tg["dates"][0])
    window = None
    if "time" in tg:
        window = (_min(tg["time"][0]), _min(tg["time"][1]) if tg["time"][1] else reserve.CLOSE_MIN)
    rows = []
    for r in analytics.free_slots(s, sc, d, None):
        if "rooms" in tg and r["room_id"] not in tg["rooms"]:
            continue
        spans = [(x["from"], x["to"]) for x in r["free"]]
        if window:
            spans = [(a, b) for a, b in spans if _min(a) <= window[0] and window[1] <= _min(b)]
        if spans:
            rows.append([f"{r['building']} {r['room']}", ", ".join(f"{a}–{b}" for a, b in spans)])
    when = md(d) + (f" {tg['time'][0]}~{tg['time'][1] or ''}" if "time" in tg else "")
    return {
        "title": f"{when} 빈 강의실 {len(rows)}곳",
        "columns": ["강의실", "빈 시간"],
        "rows": rows,
    }


def _schedule(s, sc, tg, now_local) -> dict:
    if "dates" in tg:
        days = [d_(x) for x in tg["dates"]][:SCHEDULE_DAYS_MAX]
    else:
        mon = clock.week_start(now_local.date())
        days = [mon + dt.timedelta(days=i) for i in range(7)]
    allowed = set(
        s.scalars(
            select(Room.id)
            .join(Building, Room.building_id == Building.id)
            .where(building_clause(sc), Room.id.in_(list(tg["rooms"])))
        )
    )
    rooms = [rid for rid in tg["rooms"] if rid in allowed]
    labels = room_labels(s, rooms)
    rows = []
    for rid in rooms:
        for d in days:
            items = [
                (x.s_h, x.s_m, x.e_h, x.e_m, x.type, x.subject, "정규")
                for x in s.scalars(
                    select(Slot).where(
                        Slot.room_id == rid, Slot.day == d.isoweekday(), Slot.type != 4
                    )
                )
            ]
            items += [
                (
                    r.s_h,
                    r.s_m,
                    r.e_h,
                    r.e_m,
                    r.type,
                    r.subject,
                    "승인" if r.status == "approved" else "신청",
                )
                for r in s.scalars(
                    select(Reservation).where(
                        Reservation.room_id == rid,
                        Reservation.date == d,
                        Reservation.status.in_(("approved", "requested")),
                    )
                )
            ]
            for sh, sm, eh, em, t, subj, kind in sorted(items):
                rows.append([labels[rid], md(d), span(sh, sm, eh, em), TYPE[t], subj, kind])
        q = select(ExamPeriod).where(
            ExamPeriod.room_id == rid,
            ExamPeriod.date_start <= days[-1],
            ExamPeriod.date_end >= days[0],
        )
        for x in s.scalars(q):
            rows.append(
                [labels[rid], f"{md(x.date_start)}~{md(x.date_end)}", "", "시험기간", "", ""]
            )
    return {
        "title": f"{md(days[0])}~{md(days[-1])} 일정 {len(rows)}건",
        "columns": ["강의실", "날짜", "시각", "유형", "이름", "구분"],
        "rows": rows,
    }


def _requests(s, sc, tg, now_local) -> dict:
    rows = []
    for r in admin.pending_reservations(s, sc, now_local):
        if "rooms" in tg and r["room_id"] not in tg["rooms"]:
            continue
        if "dates" in tg and r["date"].isoformat() not in tg["dates"]:
            continue
        who = (r["requester"] or {}).get("name", "-")
        rows.append(
            [
                f"{r['building']} {r['room']}",
                md(r["date"]),
                span(r["s_h"], r["s_m"], r["e_h"], r["e_m"]),
                who,
                r["subject"],
            ]
        )
    return {
        "title": f"대기 중인 신청 {len(rows)}건",
        "columns": ["강의실", "날짜", "시각", "신청자", "이름"],
        "rows": rows,
    }


def _node(s, sc, tg, now_local) -> dict:
    rows = []
    for n in admin.expected_nodes(s, sc):
        if n["room_id"] not in tg["rooms"]:
            continue
        batt = f"{n['batt_mv'] / 1000:.2f} V" if n["batt_mv"] else "-"
        rssi = f"{n['rssi']} dBm" if n["rssi"] is not None else "-"
        seen = (
            clock.to_local(n["last_seen_at"]).strftime("%m/%d %H:%M") if n["last_seen_at"] else "-"
        )
        state = ", ".join(_WARN[w] for w in n["warnings"]) or "정상"
        rows.append([f"{n['building']} {n['room']}", str(n["unit"]), batt, rssi, seen, state])
    return {
        "title": f"노드 {len(rows)}대",
        "columns": ["강의실", "유닛", "배터리", "신호", "마지막 응답", "상태"],
        "rows": rows,
    }
