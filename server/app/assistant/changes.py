"""초안(draft) → 대상 찾기 · 확정 변경 목록 · 요약 · 경고 (spec §5). DB 는 읽기만 — 쓰기는 preview.run_ops.

초안 = dialog.advance 가 만든 해석 결과 {"intent", "target": R, "set": R, "pick", "utterances"}.
R 의 키는 plan 01 Task 10 Interfaces 표 그대로."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from assistant_proto import TYPE_LABELS
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import scope
from app.auth.models import User
from app.auth.scope import Scope
from app.domain import admin, clock, reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.domain.topology import RESV_HORIZON_DAYS

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
    q = (
        select(ExamPeriod)
        .where(
            ExamPeriod.room_id == rid, ExamPeriod.date_end >= now_local.date()
        )  # 끝난 기간은 대상이 아니다
        .order_by(ExamPeriod.date_start)
    )
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


WEEKS_MAX = 6  # 한 방에 그리는 주 수 (시험기간이 길어도) — 세는 건 영향받는 주 전부
SRC_AI = 2  # AI 비서가 쓰는 슬롯 source — 이보다 큰 source(3=긴급)는 지우거나 옮기지 않는다 (포털=1 은 수동 수정이 덮을 수 있는 기존 규칙 그대로)
PROTECTED = "긴급 수업은 AI 비서로 지우거나 옮길 수 없습니다"
OPS_MAX = 150  # 한 미리보기에서 바꿀 수 있는 항목 수
MOVE_ROOM = (
    "강의실을 옮기는 변경은 지원하지 않습니다 — 새 강의실에 등록하고 기존 일정을 지워 주세요."
    " 취소하고 다시 말씀해 주세요."
)
NOOP = "바뀌는 내용이 없습니다"
TOO_MANY = f"한 번에 바꾸는 항목이 너무 많습니다 ({OPS_MAX}개 이하로 나눠 주세요)"


@dataclass
class Built:
    ops: list[dict] = field(default_factory=list)
    weeks: dict[int, list[str | None]] = field(
        default_factory=dict
    )  # 방 → 그릴 주(월요일 iso, None=정규)
    labels: dict[int, str] = field(default_factory=dict)
    summary: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def week(self, room_id: int, wk: str | None) -> None:
        lst = self.weeks.setdefault(room_id, [])
        if wk not in lst:
            lst.append(wk)

    def drawn(self, room_id: int) -> list[str | None]:
        """그릴 주 — 시간순(정규=None 이 먼저), 앞 WEEKS_MAX 개."""
        return sorted(self.weeks[room_id], key=lambda w: (w is not None, w or ""))[:WEEKS_MAX]

    @property
    def room_ids(self) -> list[int]:
        return sorted(self.weeks)


def _checks(s, b: Built, rid, d, s_min, e_min, exclude_id, type_, now_local) -> None:
    label = b.labels[rid]
    if clock.local_dt(d, s_min // 60, s_min % 60) <= now_local:
        b.blockers.append(
            f"{label} {md(d)} {s_min // 60:02d}:{s_min % 60:02d} 은 이미 지난 시각입니다."
        )
    if e_min <= s_min:
        b.blockers.append(f"{label} {md(d)}: 시작이 끝보다 늦습니다.")
    if type_ != 3:  # 휴강은 정규 수업과 겹치는 게 정상
        q = select(Slot).where(Slot.room_id == rid, Slot.day == d.isoweekday(), Slot.type != 4)
        for x in s.scalars(q):
            if _hit(x, s_min, e_min):
                b.warnings.append(
                    f'{label} 기존 수업 "{x.subject}"({WD[x.day - 1]} {span(x.s_h, x.s_m, x.e_h, x.e_m)})와 겹칩니다.'
                )
        q = select(Reservation).where(
            Reservation.room_id == rid,
            Reservation.date == d,
            Reservation.status.in_(("approved", "requested")),
        )
        if exclude_id is not None:
            q = q.where(Reservation.id != exclude_id)
        for r in s.scalars(q):
            if _hit(r, s_min, e_min):
                what = "대기 중인 학생 신청" if r.status == "requested" else "기존 일정"
                b.warnings.append(
                    f'{label} {what} "{r.subject}"({md(r.date)} {span(r.s_h, r.s_m, r.e_h, r.e_m)})와 겹칩니다.'
                )
    if d > now_local.date() + dt.timedelta(days=RESV_HORIZON_DAYS):
        b.notices.append(
            f"{md(d)} 일정은 저장해 두고 {md(d - dt.timedelta(days=RESV_HORIZON_DAYS))}부터 문 앞 화면에 보냅니다."
        )


def _new_span(old: tuple[int, int, int, int], st: dict) -> tuple[int, int, int, int] | None:
    """set.time 반영. 시작만 말했으면 원래 길이 유지. 자정을 넘으면 None."""
    if "time" not in st:
        return old
    sh, sm, eh, em = old
    nsh, nsm = hm(st["time"][0])
    if st["time"][1]:
        neh, nem = hm(st["time"][1])
    else:
        end = nsh * 60 + nsm + (eh * 60 + em) - (sh * 60 + sm)
        if end >= 24 * 60:
            return None
        neh, nem = divmod(end, 60)
    return nsh, nsm, neh, nem


def _resv_op(rid, id_, d, sp, type_, subj, prof) -> dict:
    sh, sm, eh, em = sp
    return {
        "op": "resv.put",
        "room_id": rid,
        "id": id_,
        "resv": {
            "date": d.isoformat(),
            "s_h": sh,
            "s_m": sm,
            "e_h": eh,
            "e_m": em,
            "type": type_,
            "subject": subj,
            "professor": prof,
        },
    }


def _event_add(s, b: Built, st: dict, now_local) -> None:
    if "entries" in st:  # 휴강 — 정규 수업마다 하나
        items = [
            (
                e["room_id"],
                d_(e["date"]),
                (*hm(e["start"]), *hm(e["end"])),
                e["subject"],
                e["professor"],
            )
            for e in st["entries"]
        ]
    else:
        sp = (*hm(st["time"][0]), *hm(st["time"][1]))
        items = [
            (rid, d_(iso), sp, st.get("subject", ""), st.get("professor", ""))
            for rid in st["rooms"]
            for iso in st["dates"]
        ]
    for rid, d, sp, subj, prof in items:
        sh, sm, eh, em = sp
        b.ops.append(_resv_op(rid, None, d, sp, st["type"], subj, prof))
        b.week(rid, week_of(d))
        b.summary.append(f'+ {md(d)} {span(*sp)} {TYPE[st["type"]]} "{subj}" ({b.labels[rid]})')
        _checks(s, b, rid, d, sh * 60 + sm, eh * 60 + em, None, st["type"], now_local)


def _event_change(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        r = s.get(Reservation, c["id"])
        d = d_(st["dates"][0]) if "dates" in st else r.date
        sp = _new_span((r.s_h, r.s_m, r.e_h, r.e_m), st)
        if sp is None:
            b.blockers.append(f"{b.labels[rid]} {c['label']}: 끝 시각이 자정을 넘습니다.")
            continue
        type_ = st.get("type", r.type)
        subj, prof = st.get("subject", r.subject), st.get("professor", r.professor)
        b.ops.append(_resv_op(rid, r.id, d, sp, type_, subj, prof))
        b.week(rid, week_of(r.date))
        b.week(rid, week_of(d))
        b.summary.append(
            f'~ {c["label"]} → {md(d)} {span(*sp)} {TYPE[type_]} "{subj}" ({b.labels[rid]})'
        )
        _checks(s, b, rid, d, sp[0] * 60 + sp[1], sp[2] * 60 + sp[3], r.id, type_, now_local)


def _event_remove(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        b.ops.append({"op": "resv.del", "room_id": rid, "id": c["id"]})
        b.week(rid, week_of(d_(c["date"])))
        b.summary.append(f"− {c['label']} ({b.labels[rid]})")


def _exam_weeks(b: Built, rid: int, a: dt.date, z: dt.date) -> None:
    mon = clock.week_start(a)
    while mon <= z:
        b.week(rid, mon.isoformat())
        mon += dt.timedelta(days=7)


def _exam_add(s, b: Built, st: dict, now_local) -> None:
    a, z = d_(st["range"][0]), d_(st["range"][1])
    if z < now_local.date():
        b.blockers.append(f"{md(a)}~{md(z)} 은 이미 지난 기간입니다.")
    for rid in st["rooms"]:
        b.ops.append(
            {
                "op": "exam.put",
                "room_id": rid,
                "id": None,
                "exam": {"date_start": a.isoformat(), "date_end": z.isoformat()},
            }
        )
        _exam_weeks(b, rid, a, z)
        b.summary.append(f"+ 시험기간 {md(a)}~{md(z)} ({b.labels[rid]})")


def _exam_change(s, b: Built, ch: dict, st: dict, now_local) -> None:
    a, z = d_(st["range"][0]), d_(st["range"][1])
    if z < now_local.date():
        b.blockers.append(f"{md(a)}~{md(z)} 은 이미 지난 기간입니다.")
    for rid, c in ch.items():
        b.ops.append(
            {
                "op": "exam.put",
                "room_id": rid,
                "id": c["id"],
                "exam": {"date_start": a.isoformat(), "date_end": z.isoformat()},
            }
        )
        _exam_weeks(b, rid, d_(c["start"]), d_(c["end"]))
        _exam_weeks(b, rid, a, z)
        b.summary.append(f"~ 시험기간 {c['label']} → {md(a)}~{md(z)} ({b.labels[rid]})")


def _exam_remove(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        b.ops.append({"op": "exam.del", "room_id": rid, "id": c["id"]})
        _exam_weeks(b, rid, d_(c["start"]), d_(c["end"]))
        b.summary.append(f"− 시험기간 {c['label']} ({b.labels[rid]})")


def _slot_clash(s, b: Built, rid: int, day: int, sp, skip_id: int | None) -> None:
    """같은 요일 다른 수업과의 겹침·덮어쓰기 경고. 시작이 같으면 put 이 그 수업을 덮어쓴다."""
    sh, sm, eh, em = sp
    label = b.labels[rid]
    for x in s.scalars(select(Slot).where(Slot.room_id == rid, Slot.day == day)):
        if x.id == skip_id:
            continue
        where = f"{WD[day - 1]} {span(x.s_h, x.s_m, x.e_h, x.e_m)}"
        if (x.s_h, x.s_m) == (sh, sm):
            if x.source > SRC_AI:  # put_slot 이 거부할 덮어쓰기 — 날것 409 대신 안내
                b.blockers.append(f"{label} {where} {x.subject}: {PROTECTED}")
                continue
            b.warnings.append(f'{label} 기존 수업 "{x.subject}"({where})을 바꿉니다.')
            b.summary.append(f"− 매주 {where} {x.subject} ({label})")
        if _hit(x, sh * 60 + sm, eh * 60 + em):
            b.warnings.append(f'{label} 기존 수업 "{x.subject}"({where})와 겹칩니다.')


def _class_add(s, b: Built, st: dict, now_local) -> None:
    sh, sm, eh, em = (*hm(st["time"][0]), *hm(st["time"][1]))
    type_ = st.get("type", 1)
    if eh * 60 + em <= sh * 60 + sm:
        b.blockers.append("시작이 끝보다 늦습니다.")
    for rid in st["rooms"]:
        for wd in st["weekdays"]:
            n = len(b.blockers)
            _slot_clash(s, b, rid, wd, (sh, sm, eh, em), None)
            if len(b.blockers) > n:  # 긴급 수업을 덮어쓰려 함 — put 은 하지 않는다
                continue
            b.ops.append(
                {
                    "op": "slot.put",
                    "room_id": rid,
                    "slot": {
                        "day": wd,
                        "s_h": sh,
                        "s_m": sm,
                        "e_h": eh,
                        "e_m": em,
                        "type": type_,
                        "subject": st["subject"],
                        "professor": st.get("professor", ""),
                        "source": 2,
                    },
                }
            )
            b.week(rid, None)
            b.summary.append(
                f'+ 매주 {WD[wd - 1]} {span(sh, sm, eh, em)} {TYPE[type_]} "{st["subject"]}" ({b.labels[rid]})'
            )


def _class_change(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        x = s.scalar(
            select(Slot).where(
                Slot.room_id == rid,
                Slot.day == c["day"],
                Slot.s_h == c["s_h"],
                Slot.s_m == c["s_m"],
            )
        )
        day = st["weekdays"][0] if "weekdays" in st else x.day
        sp = _new_span((x.s_h, x.s_m, x.e_h, x.e_m), st)
        if sp is None:
            b.blockers.append(f"{b.labels[rid]} {c['label']}: 끝 시각이 자정을 넘습니다.")
            continue
        sh, sm, eh, em = sp
        new = {
            "day": day,
            "s_h": sh,
            "s_m": sm,
            "e_h": eh,
            "e_m": em,
            "type": st.get("type", x.type),
            "subject": st.get("subject", x.subject),
            "professor": st.get("professor", x.professor),
            "source": 2,
        }
        moving = (day, sh, sm) != (x.day, x.s_h, x.s_m)
        if x.source > SRC_AI:
            b.blockers.append(f"{b.labels[rid]} {c['label']}: {PROTECTED}")
            continue
        n = len(b.blockers)
        _slot_clash(s, b, rid, day, sp, x.id)
        if len(b.blockers) > n:  # 긴급 수업 위로 옮기려 함 — del·put 은 하지 않는다
            continue
        if moving:
            b.ops.append(
                {"op": "slot.del", "room_id": rid, "day": x.day, "s_h": x.s_h, "s_m": x.s_m}
            )
        b.ops.append({"op": "slot.put", "room_id": rid, "slot": new})
        b.week(rid, None)
        b.summary.append(
            f"~ 매주 {c['label']} → {WD[day - 1]} {span(*sp)} {new['subject']} {new['professor']} ({b.labels[rid]})".rstrip()
        )


def _class_remove(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        x = s.scalar(
            select(Slot).where(
                Slot.room_id == rid,
                Slot.day == c["day"],
                Slot.s_h == c["s_h"],
                Slot.s_m == c["s_m"],
            )
        )
        if x is not None and x.source > SRC_AI:
            b.blockers.append(f"{b.labels[rid]} {c['label']}: {PROTECTED}")
            continue
        b.ops.append(
            {"op": "slot.del", "room_id": rid, "day": c["day"], "s_h": c["s_h"], "s_m": c["s_m"]}
        )
        b.week(rid, None)
        b.summary.append(f"− 매주 {c['label']} ({b.labels[rid]})")


def _request(b: Built, ch: dict, st: dict, approve: bool) -> None:
    for c in ch.values():
        rid = c["room_id"]
        if approve:
            b.ops.append({"op": "request.approve", "room_id": rid, "id": c["id"]})
            b.summary.append(f"✓ 승인 {c['label']}")
        else:
            reason = st.get("reason", "관리자 거절")
            b.ops.append({"op": "request.reject", "room_id": rid, "id": c["id"], "reason": reason})
            b.summary.append(f"✗ 거절 {c['label']} — {reason}")
        b.week(rid, week_of(d_(c["date"])))


_BUILD = {
    "event.change": _event_change,
    "event.remove": _event_remove,
    "exam.change": _exam_change,
    "exam.remove": _exam_remove,
    "class.change": _class_change,
    "class.remove": _class_remove,
}


def plan(s: Session, sc: Scope, draft: dict, now_local: dt.datetime) -> Built:
    it, tg, st = draft["intent"], draft["target"], draft["set"]
    b = Built()
    cands: dict[int, list[dict]] = {}
    ch: dict[int, dict] = {}
    if not it.endswith(".add"):
        cands = find_candidates(s, sc, draft, now_local)
        ch = chosen(cands, draft["pick"])
    ids = set(st.get("rooms", [])) | set(tg.get("rooms", []))
    ids |= {c["room_id"] for c in ch.values() if "room_id" in c}
    b.labels = room_labels(s, ids)
    for rid, lst in cands.items():
        if rid and not lst:
            b.notices.append(f"{b.labels[rid]}: 해당 항목이 없어 건너뜁니다.")
    if it.endswith(".change") and "rooms" in st:
        b.blockers.append(MOVE_ROOM)
    elif it == "event.add":
        _event_add(s, b, st, now_local)
    elif it == "exam.add":
        _exam_add(s, b, st, now_local)
    elif it == "class.add":
        _class_add(s, b, st, now_local)
    elif it in ("request.approve", "request.reject"):
        _request(b, ch, st, it == "request.approve")
    else:
        _BUILD[it](s, b, ch, st, now_local)
    if not b.blockers and not b.ops:
        b.blockers.append(NOOP)
    if len(b.ops) > OPS_MAX:
        b.blockers.append(TOO_MANY)
    rooms_now = set(b.room_ids)
    for n in admin.expected_nodes(s, sc):
        if n["room_id"] in rooms_now and "unseen" in n["warnings"]:
            b.warnings.append(
                f"{b.labels[n['room_id']]} 노드가 응답하지 않습니다 — 연결되면 전송됩니다."
            )
    b.warnings = list(dict.fromkeys(b.warnings))
    b.notices = list(dict.fromkeys(b.notices))
    b.blockers = list(dict.fromkeys(b.blockers))
    return b
