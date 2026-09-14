"""v2 §8.6 — 웹이 호출하는 유일한 진입점. 동기, 자체 세션, 한 트랜잭션 (spec §4.2).

lora_service 는 domain 을 import 하지 않는다. 방·모뎀 조회는 Topology, FILE 레코드는 RecordProvider,
허브 호출은 HubPort — 셋 다 기동 시 주입된다.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from lora_proto import codec as C
from sqlalchemy import select
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


def enqueue_slot_del(
    bld: str, room: int, day: int, start: tuple[int, int], unit: int = 0
) -> list[int]:
    return _enqueue(bld, room, unit, "SLOT_DEL", lambda v: C.SlotDel(v, day, start[0], start[1]))


def enqueue_day_clear(bld: str, room: int, day: int, unit: int = 0) -> list[int]:
    return _enqueue(bld, room, unit, "DAY_CLEAR", lambda v: C.DayClear(v, day))


def enqueue_resv_set(
    bld: str,
    room: int,
    resv_id: int,
    date: dt.date,
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
        "RESV_SET",
        lambda v: C.ResvSet(
            v,
            resv_id,
            date.year,
            date.month,
            date.day,
            start[0],
            start[1],
            end[0],
            end[1],
            type_,
            subject,
            professor,
        ),
    )


def enqueue_resv_del(bld: str, room: int, resv_id: int, unit: int = 0) -> list[int]:
    return _enqueue(bld, room, unit, "RESV_DEL", lambda v: C.ResvDel(v, resv_id))


def enqueue_exam_set(
    bld: str, room: int, exam_id: int, date_start: dt.date, date_end: dt.date, unit: int = 0
) -> list[int]:
    return _enqueue(
        bld,
        room,
        unit,
        "EXAM_SET",
        lambda v: C.ExamSet(
            v,
            exam_id,
            date_start.year,
            date_start.month,
            date_start.day,
            date_end.year,
            date_end.month,
            date_end.day,
        ),
    )


def enqueue_exam_del(bld: str, room: int, exam_id: int, unit: int = 0) -> list[int]:
    return _enqueue(bld, room, unit, "EXAM_DEL", lambda v: C.ExamDel(v, exam_id))


def enqueue_cmd(bld: str, room: int, cmd: int, args: bytes = b"", unit: int = 0) -> list[int]:
    return _enqueue(bld, room, unit, "CMD", lambda v: C.Cmd(cmd, args))


FILE_KIND = {"schedule": 1, "resv": 2, "exam": 3}


def _enqueue_file(
    s: Session, info: RoomInfo, bld: str, room: int, unit: int, kind: str
) -> list[int]:
    """kind 전체 재동기 FILE. 같은 (bld,room,unit,kind) 에 queued|dispatched FILE 이 있으면 그 id (v2 §8.3)."""
    units = [unit] if unit else list(range(1, info.units + 1))
    open_rows = s.scalars(
        select(Outbox).where(
            Outbox.bld == bld,
            Outbox.room == room,
            Outbox.unit.in_(units),
            Outbox.type == "FILE",
            Outbox.state.in_(("queued", "dispatched")),
        )
    ).all()
    existing = [r.id for r in open_rows if json.loads(r.payload)["kind"] == FILE_KIND[kind]]
    if existing:
        return existing
    new_ver = _bump_ver(s, bld, room, kind)
    records = _records(bld, room, kind)
    C.build_file(FILE_KIND[kind], records, new_ver)  # 크기·kind 검증
    payload = json.dumps(
        {"kind": FILE_KIND[kind], "records": [json.loads(_to_json(r)) for r in records]},
        ensure_ascii=False,
    )
    return _insert(s, info, bld, room, unit, "FILE", payload, new_ver)


def enqueue_full_sync(
    bld: str, room: int, kinds: tuple[str, ...] = ("schedule", "resv", "exam"), unit: int = 0
) -> list[int]:
    info = _room(bld, room)
    ids: list[int] = []
    with _Session() as s, s.begin():
        for kind in kinds:
            ids += _enqueue_file(s, info, bld, room, unit, kind)
    if info.modem_id:
        _hub.notify(info.modem_id)
    return ids


def provision(mac: str, bld: str, room: int, unit: int) -> int:
    if unit not in (1, 2):
        raise ValueError("unit 은 1 또는 2")
    return _enqueue(
        bld,
        room,
        unit,
        "SET_ROOM",
        lambda v: C.SetRoom(v, bytes.fromhex(mac), ord(bld), room, unit),
    )[0]


def request_time_broadcast() -> int:
    return _hub.time_now()


def get_outbox(
    state: str | None = None, bld: str | None = None, room: int | None = None, limit: int = 100
) -> list[Outbox]:
    q = select(Outbox).order_by(Outbox.id.desc()).limit(limit)
    if state:
        q = q.where(Outbox.state == state)
    if bld:
        q = q.where(Outbox.bld == bld)
    if room is not None:
        q = q.where(Outbox.room == room)
    with _Session() as s:
        return list(reversed(s.scalars(q).all()))


def cancel(outbox_id: int) -> bool:
    """queued → cancelled. dispatched 는 모뎀Pi 에 cancel 을 보내고 job_result 를 기다린다 (spec §2.4)."""
    with _Session() as s, s.begin():
        row = s.get(Outbox, outbox_id)
        if row is None:
            return False
        if row.state == "queued":
            row.state = "cancelled"
            row.finished_at = utcnow()
            return True
        if row.state == "dispatched" and row.modem_id:
            _hub.cancel(row.modem_id, row.id)
            return True
        return False
