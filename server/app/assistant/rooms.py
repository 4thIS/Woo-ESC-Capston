"""강의실 표현 → 방 (spec §4). 범위(scope) 안 방만 본다 — 범위 밖·다른 학교 방은 없는 것과 같다."""

from __future__ import annotations

import re
from dataclasses import dataclass

from assistant_proto import normalize_room
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import scope
from app.auth.scope import Scope
from app.domain.models import Building, Room

# 맨 끝의 호수 부분 — 층 · 범위 · 호수. 앞은 건물 표현(숫자로 끝나면 안 된다: "5호관" 의 5 와 호수를 가른다).
_TAIL = re.compile(
    r"(?P<floor>\d{1,2})층(?:전체)?$|(?P<a>\d{1,4})[~\-](?P<b>\d{1,4})$|(?P<n>\d{1,4})$"
)


@dataclass(frozen=True)
class RoomRef:
    id: int
    building_id: int
    building: str
    bld: str
    room: int

    @property
    def label(self) -> str:
        return f"{self.building} {self.room}"


@dataclass(frozen=True)
class Found:
    rooms: tuple[RoomRef, ...]


@dataclass(frozen=True)
class Ambiguous:
    expr: str
    options: tuple[tuple[str, str], ...]  # (선택지 id, 라벨)


@dataclass(frozen=True)
class Missing:
    expr: str


def scoped_rooms(s: Session, sc: Scope) -> list[RoomRef]:
    q = (
        select(Room, Building)
        .join(Building, Room.building_id == Building.id)
        .where(scope.building_clause(sc))
        .order_by(Building.id, Room.room)
    )
    return [RoomRef(r.id, b.id, b.name, b.bld, r.room) for r, b in s.execute(q).all()]


def _bkey(x: str) -> str:
    return x.casefold().removesuffix("동")


def resolve_room_expr(
    s: Session, sc: Scope, expr: str, *, only_building: int | None = None
) -> Found | Ambiguous | Missing:
    # 공백은 전부 없애고 비교한다 — "공학관803" · "공학관 803호" · "5호관 201" 이 같은 방식으로 읽힌다.
    compact = "".join(normalize_room(expr).split())
    m = _TAIL.search(compact)
    bexpr = compact[: m.start()] if m else compact
    if bexpr[-1:].isdigit():  # "공학관12345" 처럼 호수 앞이 숫자면 읽을 수 없다
        return Missing(expr)
    refs = scoped_rooms(s, sc)
    if only_building is not None:
        refs = [r for r in refs if r.building_id == only_building]
    if bexpr:
        k = _bkey(bexpr)
        refs = [
            r
            for r in refs
            if k
            and (
                k == _bkey("".join(r.building.split()))
                or k == r.bld.casefold()
                or _bkey("".join(r.building.split())).startswith(k)
            )
        ]
    label = ""
    if m is None:  # 건물 이름만 — 그 건물 전체
        hits, many = (refs if bexpr else []), True
    elif m.group("n"):
        hits, many = [r for r in refs if r.room == int(m.group("n"))], False
    elif m.group("a"):
        a, b = sorted((int(m.group("a")), int(m.group("b"))))
        label = f"{a}~{b}"
        # 범위는 한 건물 안에서 읽는다 — 양 끝 호수가 다 있는 건물이 있으면 그 건물들만.
        full = {
            bid
            for bid in {r.building_id for r in refs}
            if {a, b} <= {r.room for r in refs if r.building_id == bid}
        }
        pool = [r for r in refs if r.building_id in full] if full else refs
        hits, many = [r for r in pool if a <= r.room <= b], True
    else:
        floor = int(m.group("floor"))
        label = f"{floor}층"
        hits, many = [r for r in refs if r.room // 100 == floor], True
    if not hits:
        return Missing(expr)
    blds = list(dict.fromkeys(r.building_id for r in hits))
    if len(blds) == 1:
        return Found(tuple(hits))
    if not many:
        return Ambiguous(expr, tuple((f"room:{r.id}", r.label) for r in hits))
    names = {r.building_id: r.building for r in hits}
    return Ambiguous(
        expr,
        tuple(
            (
                f"bld:{b}",
                f"{names[b]} {label} ({sum(r.building_id == b for r in hits)}개)"
                if label
                else f"{names[b]} ({sum(r.building_id == b for r in hits)}개)",
            )
            for b in blds
        ),
    )
