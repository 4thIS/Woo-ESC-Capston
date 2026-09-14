"""v2 §8.6 — 웹이 호출하는 유일한 진입점. 동기, 자체 세션, 한 트랜잭션 (spec §4.2).

lora_service 는 domain 을 import 하지 않는다. 방·모뎀 조회는 Topology, FILE 레코드는 RecordProvider,
허브 호출은 HubPort — 셋 다 기동 시 주입된다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from lora_proto import codec as C
from sqlalchemy.orm import Session, sessionmaker

from app.db import utcnow
from app.lora_service.models import Outbox, RoomVersion


@dataclass(frozen=True)
class RoomInfo:
    modem_id: str | None
    units: int
    net_id: int


class Topology(Protocol):
    def room(self, bld: str, room: int) -> RoomInfo | None: ...
    def nodes(self, modem_id: str) -> list[tuple[str, int, int]]: ...
    def net_id(self, modem_id: str) -> int | None: ...


class HubPort(Protocol):
    def notify(self, modem_id: str) -> None: ...
    def config_changed(self, modem_id: str) -> None: ...
    def time_now(self) -> int: ...
    def cancel(self, modem_id: str, job_id: int) -> None: ...


class NullHub:
    def notify(self, modem_id: str) -> None:
        pass

    def config_changed(self, modem_id: str) -> None:
        pass

    def time_now(self) -> int:
        return 0

    def cancel(self, modem_id: str, job_id: int) -> None:
        pass


RecordProvider = Callable[[str, int, str], list]  # (bld, room, kind) -> codec dataclass 목록


class NotFound(LookupError):
    pass


def _no_records(bld: str, room: int, kind: str) -> list:
    return []


_Session: sessionmaker | None = None
_topology: Topology | None = None
_records: RecordProvider = _no_records
_hub: HubPort = NullHub()


def configure(session_factory: sessionmaker) -> None:
    global _Session
    _Session = session_factory


def set_topology(t: Topology) -> None:
    global _topology
    _topology = t


def set_record_provider(fn: RecordProvider) -> None:
    global _records
    _records = fn


def set_hub(port: HubPort) -> None:
    global _hub
    _hub = port


def config_changed(modem_id: str) -> None:
    """domain 이 rooms/buildings 를 바꿨을 때. 허브가 config 를 재송한다."""
    _hub.config_changed(modem_id)


PRIORITY = {  # v2 §8.2
    "TIME": 0,
    "RESV_SET": 1,
    "RESV_DEL": 1,
    "SLOT_SET": 3,
    "SLOT_DEL": 3,
    "DAY_CLEAR": 3,
    "EXAM_SET": 3,
    "EXAM_DEL": 3,
    "CMD": 3,
    "SET_ROOM": 3,
    "FILE": 5,
}
KIND_OF = {  # 버전이 붙는 TYPE → room_versions.kind
    "SLOT_SET": "schedule",
    "SLOT_DEL": "schedule",
    "DAY_CLEAR": "schedule",
    "RESV_SET": "resv",
    "RESV_DEL": "resv",
    "EXAM_SET": "exam",
    "EXAM_DEL": "exam",
    "SET_ROOM": "ident",
}


def _room(bld: str, room: int) -> RoomInfo:
    info = _topology.room(bld, room)
    if info is None:
        raise NotFound(f"room {bld}{room}")
    return info


def _bump_ver(s: Session, bld: str, room: int, kind: str) -> int:
    rv = s.get(RoomVersion, (bld, room, kind))
    if rv is None:
        rv = RoomVersion(bld=bld, room=room, kind=kind, ver=0)
        s.add(rv)
    rv.ver = rv.ver % 255 + 1  # 1..255 롤링, 0 건너뜀 (v2 §8.3)
    return rv.ver


def _to_json(obj: object) -> str:
    """codec dataclass → job.payload. new_ver 제외, bytes 는 hex (spec §2.4)."""
    d = {
        k: (v.hex() if isinstance(v, bytes) else v)
        for k, v in asdict(obj).items()
        if k != "new_ver"
    }
    return json.dumps(d, ensure_ascii=False)


def _insert(
    s: Session,
    info: RoomInfo,
    bld: str,
    room: int,
    unit: int,
    type_: str,
    payload: str,
    new_ver: int | None,
) -> list[int]:
    units = [unit] if unit else list(range(1, info.units + 1))  # unit=0 → 유닛 분해
    rows = [
        Outbox(
            modem_id=info.modem_id,
            bld=bld,
            room=room,
            unit=u,
            type=type_,
            payload=payload,
            priority=PRIORITY[type_],
            new_ver=new_ver,
            created_at=utcnow(),
        )
        for u in units
    ]
    s.add_all(rows)
    s.flush()
    return [r.id for r in rows]


def _enqueue(
    bld: str, room: int, unit: int, type_: str, make: Callable[[int | None], object]
) -> list[int]:
    """버전 +1 → codec 객체 생성·인코딩(검증) → outbox 삽입. 전부 한 트랜잭션."""
    info = _room(bld, room)
    with _Session() as s, s.begin():
        kind = KIND_OF.get(type_)
        new_ver = _bump_ver(s, bld, room, kind) if kind else None
        obj = make(new_ver)
        C.encode_payload(
            obj
        )  # FrameError(ValueError) 면 여기서 롤백 — 모뎀Pi의 bad_payload 를 서버에서 막는다
        ids = _insert(s, info, bld, room, unit, type_, _to_json(obj), new_ver)
    if info.modem_id:
        _hub.notify(info.modem_id)
    return ids


# ---------- v2 §8.6 ----------


def enqueue_slot_set(
    bld: str,
    room: int,
    day: int,
    start: tuple[int, int],
    end: tuple[int, int],
    type_: int,
    subject: str,
    professor: str,
    unit: int = 0,
) -> list[int]:
    return _enqueue(
        bld,
        room,
        unit,
        "SLOT_SET",
        lambda v: C.SlotSet(v, day, start[0], start[1], end[0], end[1], type_, subject, professor),
    )
