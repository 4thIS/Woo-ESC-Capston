"""시간표 CSV 임포트 (S2b spec §2). 도메인 모델만 안다 — outbox 는 라우터가 넣는다."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field

from lora_proto import proto as P
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Building, Room, School, Slot

COLUMNS = ("school", "building", "room", "day", "start", "end", "type", "subject", "professor")
DAYS = "월화수목금토일"
TYPES = ("수업", "시험", "휴강", "빈강의실", "특강", "대여")
MAX_ERRORS = 100
NODE_SLOT_MAX = 48  # v2 §12
_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class Row:
    row: int  # 파일 행 번호 (헤더 = 1)
    room_id: int
    bld: str
    room: int
    day: int
    s_h: int
    s_m: int
    e_h: int
    e_m: int
    type: int
    subject: str
    professor: str


@dataclass(frozen=True)
class RowError:
    row: int
    error: str


def _day(v: str) -> int | None:
    if len(v) == 1 and v in DAYS:
        return DAYS.index(v) + 1
    return int(v) if v.isdigit() and 1 <= int(v) <= 7 else None


def _type(v: str) -> int | None:
    if v in TYPES:
        return TYPES.index(v) + 1
    return int(v) if v.isdigit() and 1 <= int(v) <= 6 else None


def _hhmm(v: str) -> tuple[int, int] | None:
    m = _HHMM.match(v)
    if not m:
        return None
    h, mi = int(m[1]), int(m[2])
    return (h, mi) if h <= 23 and mi <= 59 else None


def _bytes(s: str) -> int:
    return len(s.encode("utf-8"))


class _Lookup:
    """학교 이름 → bld → room 번호 → (room_id, bld, room). 한 번 읽어 dict 로."""

    def __init__(self, s: Session):
        self.rooms: dict[tuple[str, str, int], int] = {}
        self.schools: set[str] = set()
        self.blds: set[tuple[str, str]] = set()
        q = (
            select(School.name, Building.bld, Room.room, Room.id)
            .join(Building, Building.school_id == School.id)
            .join(Room, Room.building_id == Building.id)
        )
        for name, bld, room, rid in s.execute(q):
            self.rooms[(name, bld, room)] = rid
        for name, bld in s.execute(select(School.name, Building.bld).join(Building)):
            self.schools.add(name)
            self.blds.add((name, bld))
        for name in s.scalars(select(School.name)):
            self.schools.add(name)


def _row(n: int, rec: dict[str, str], lk: _Lookup) -> Row | RowError:
    school, bld = rec["school"], rec["building"]
    if school not in lk.schools:
        return RowError(n, f"school: '{school}' 없음")
    if (school, bld) not in lk.blds:
        return RowError(n, f"building: '{bld}' 없음 ({school})")
    if not (rec["room"].isdigit() and 1 <= int(rec["room"]) <= 9999):
        return RowError(n, f"room: '{rec['room']}' 은 1~9999")
    room = int(rec["room"])
    rid = lk.rooms.get((school, bld, room))
    if rid is None:
        return RowError(n, f"room: {room} 없음 ({school} {bld})")
    day = _day(rec["day"])
    if day is None:
        return RowError(n, f"day: '{rec['day']}' 은 월~일 또는 1~7")
    start, end = _hhmm(rec["start"]), _hhmm(rec["end"])
    if start is None:
        return RowError(n, f"start: '{rec['start']}' 은 HH:MM")
    if end is None:
        return RowError(n, f"end: '{rec['end']}' 은 HH:MM")
    if end <= start:
        return RowError(n, f"end {end[0]:02d}:{end[1]:02d} ≤ start {start[0]:02d}:{start[1]:02d}")
    type_ = _type(rec["type"])
    if type_ is None:
        return RowError(n, f"type: '{rec['type']}' 은 수업~대여 또는 1~6")
    if _bytes(rec["subject"]) > P.SUBJ_MAX:
        return RowError(n, f"subject {_bytes(rec['subject'])} B > {P.SUBJ_MAX} B (UTF-8)")
    if _bytes(rec["professor"]) > P.PROF_MAX:
        return RowError(n, f"professor {_bytes(rec['professor'])} B > {P.PROF_MAX} B (UTF-8)")
    return Row(n, rid, bld, room, day, *start, *end, type_, rec["subject"], rec["professor"])


def parse(text: str, s: Session) -> tuple[list[Row], list[RowError]]:
    """CSV 텍스트 → Row 목록. errors 가 비어 있지 않으면 rows 는 쓰지 않는다 (all-or-nothing)."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip().lower() for h in next(reader, [])]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        return [], [RowError(0, f"헤더에 없는 컬럼: {', '.join(missing)}")]
    idx = {c: header.index(c) for c in COLUMNS}
    lk = _Lookup(s)
    rows: list[Row] = []
    errors: list[RowError] = []
    seen: dict[tuple[int, int, int, int], int] = {}  # (room_id, day, s_h, s_m) → row
    for n, raw in enumerate(reader, start=2):
        if not any(c.strip() for c in raw):
            continue
        if len(errors) >= MAX_ERRORS:
            break
        rec = {c: (raw[i].strip() if i < len(raw) else "") for c, i in idx.items()}
        r = _row(n, rec, lk)
        if isinstance(r, RowError):
            errors.append(r)
            continue
        key = (r.room_id, r.day, r.s_h, r.s_m)
        if key in seen:
            errors.append(
                RowError(
                    n,
                    f"row {seen[key]} 와 중복 ({r.room} {DAYS[r.day - 1]} {r.s_h:02d}:{r.s_m:02d})",
                )
            )
            continue
        seen[key] = n
        rows.append(r)
    if errors:
        return rows, errors
    # 노드 슬롯 상한: 포털 행 + 그 방에 남을 source≥2 슬롯 (겹치는 키는 포털 행이 skip 되므로 한 번만)
    by_room: dict[int, set[tuple[int, int, int]]] = defaultdict(set)
    for r in rows:
        by_room[r.room_id].add((r.day, r.s_h, r.s_m))
    for rid, keys in by_room.items():
        kept = s.scalars(select(Slot).where(Slot.room_id == rid, Slot.source >= 2)).all()
        total = len(keys | {(x.day, x.s_h, x.s_m) for x in kept})
        if total > NODE_SLOT_MAX:
            room_no = next(r.room for r in rows if r.room_id == rid)
            errors.append(RowError(0, f"{room_no}: 슬롯 {total} 개 > {NODE_SLOT_MAX} (노드 상한)"))
    return rows, errors


SOURCE_NAME = {1: "포털", 2: "수동", 3: "긴급"}


@dataclass
class Summary:
    rooms: int = 0
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: list[dict] = field(default_factory=list)
    changed: list[tuple[str, int]] = field(default_factory=list)  # FILE 대상 (bld, room)


def apply(rows: list[Row], s: Session, dry_run: bool = False) -> Summary:
    """방마다 source=1 슬롯을 파일 내용으로 교체 (S2b §2.3). 커밋은 호출 측. dry_run 이면 세지만 쓰지 않는다."""
    sm = Summary()
    by_room: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        by_room[r.room_id].append(r)
    for rid, rs in by_room.items():
        existing = {
            (x.day, x.s_h, x.s_m): x for x in s.scalars(select(Slot).where(Slot.room_id == rid))
        }
        file_keys = {(r.day, r.s_h, r.s_m) for r in rs}
        changed = False
        for key, x in existing.items():
            if x.source == 1 and key not in file_keys:
                sm.deleted += 1
                changed = True
                if not dry_run:
                    s.delete(x)
        for r in rs:
            x = existing.get((r.day, r.s_h, r.s_m))
            if x is not None and x.source >= 2:
                sm.skipped.append(
                    {
                        "row": r.row,
                        "reason": f"{SOURCE_NAME[x.source]} 슬롯 있음 (source={x.source})",
                    }
                )
                continue
            changed = True
            if x is None:
                sm.added += 1
                x = Slot(room_id=rid, day=r.day, s_h=r.s_h, s_m=r.s_m, source=1)
                if not dry_run:
                    s.add(x)
            else:
                sm.updated += 1
            if not dry_run:
                x.e_h, x.e_m, x.type, x.subject, x.professor = (
                    r.e_h,
                    r.e_m,
                    r.type,
                    r.subject,
                    r.professor,
                )
        if changed:
            sm.rooms += 1
            sm.changed.append((rs[0].bld, rs[0].room))
    if not dry_run:
        s.flush()
    return sm
