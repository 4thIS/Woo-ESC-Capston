"""v2 §8.6 — 웹이 호출하는 유일한 진입점. 동기, 자체 세션, 한 트랜잭션 (spec §4.2).

lora_service 는 domain 을 import 하지 않는다. 방·모뎀 조회는 Topology, FILE 레코드는 RecordProvider,
허브 호출은 HubPort — 셋 다 기동 시 주입된다.

`enqueue_*` 8개는 키워드 `session=` 을 받으면 호출자 트랜잭션에서 flush 까지만 하고,
커밋·`api.notify(modem_id)` 는 호출자 몫이다(#9). `session` 생략 시(기본 None)는 기존대로
자체 세션에서 커밋까지 하고 알린다 — additive, 이 경로는 그대로다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from lora_proto import codec as C
from lora_proto import jsonio
from lora_proto import proto as P
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db import utcnow
from app.lora_service.models import Modem, Outbox, PendingDevice, RoomVersion, TerminalStatus

log = logging.getLogger("lora_api")


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


class ValidationError(ValueError):
    """입력 검증 실패 → 라우터가 400. 그 밖의 ValueError 는 내부 버그라 500 으로 드러낸다 (#8)."""


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


def get_topology() -> Topology:
    return _topology


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
    """codec dataclass → job.payload. 변환 규칙은 lora_proto.jsonio 하나뿐(로드맵 §4.2) — new_ver 만 뺀다."""
    return json.dumps(jsonio.to_json(obj, drop=("new_ver",)), ensure_ascii=False)


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
    bld: str,
    room: int,
    unit: int,
    type_: str,
    make: Callable[[int | None], object],
    session: Session | None = None,
) -> list[int]:
    """버전 +1 → codec 객체 생성·인코딩(검증) → outbox 삽입. 전부 한 트랜잭션.
    `session` 이 주어지면 그 안에서 flush 까지만 — 커밋·notify 는 호출자 몫(#9 원자화).
    호출자는 커밋 뒤 `notify(modem_id)` 를 불러야 허브가 새 작업을 본다.
    예외 시 호출자는 롤백해야 한다 — 잡고 커밋하면 버전만 오르고 outbox 행은 없는 상태가 남는다."""
    info = _room(bld, room)

    def body(s: Session) -> list[int]:
        kind = KIND_OF.get(type_)
        new_ver = _bump_ver(s, bld, room, kind) if kind else None
        obj = make(new_ver)
        try:
            C.encode_payload(obj)  # 실패면 여기서 롤백 — 모뎀Pi의 bad_payload 를 서버에서 막는다
        except C.FrameError as e:
            raise ValidationError(str(e)) from e
        return _insert(s, info, bld, room, unit, type_, _to_json(obj), new_ver)

    if session is not None:
        return body(session)
    with _Session() as s, s.begin():
        ids = body(s)
    if info.modem_id:
        _hub.notify(info.modem_id)
    return ids


def notify(modem_id: str | None) -> None:
    """라우터가 s.commit() 한 뒤 직접 부른다 (session 모드의 짝). _hub.notify 는 call_soon_threadsafe 라 threadpool 에서도 안전."""
    if modem_id:
        _hub.notify(modem_id)


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
    *,
    session: Session | None = None,
) -> list[int]:
    return _enqueue(
        bld,
        room,
        unit,
        "SLOT_SET",
        lambda v: C.SlotSet(v, day, start[0], start[1], end[0], end[1], type_, subject, professor),
        session,
    )


def enqueue_slot_del(
    bld: str,
    room: int,
    day: int,
    start: tuple[int, int],
    unit: int = 0,
    *,
    session: Session | None = None,
) -> list[int]:
    return _enqueue(
        bld, room, unit, "SLOT_DEL", lambda v: C.SlotDel(v, day, start[0], start[1]), session
    )


def enqueue_day_clear(
    bld: str, room: int, day: int, unit: int = 0, *, session: Session | None = None
) -> list[int]:
    return _enqueue(bld, room, unit, "DAY_CLEAR", lambda v: C.DayClear(v, day), session)


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
    *,
    session: Session | None = None,
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
        session,
    )


def enqueue_resv_del(
    bld: str, room: int, resv_id: int, unit: int = 0, *, session: Session | None = None
) -> list[int]:
    return _enqueue(bld, room, unit, "RESV_DEL", lambda v: C.ResvDel(v, resv_id), session)


def enqueue_exam_set(
    bld: str,
    room: int,
    exam_id: int,
    date_start: dt.date,
    date_end: dt.date,
    unit: int = 0,
    *,
    session: Session | None = None,
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
        session,
    )


def enqueue_exam_del(
    bld: str, room: int, exam_id: int, unit: int = 0, *, session: Session | None = None
) -> list[int]:
    return _enqueue(bld, room, unit, "EXAM_DEL", lambda v: C.ExamDel(v, exam_id), session)


def enqueue_cmd(
    bld: str,
    room: int,
    cmd: int,
    args: bytes = b"",
    unit: int = 0,
    *,
    session: Session | None = None,
) -> list[int]:
    return _enqueue(bld, room, unit, "CMD", lambda v: C.Cmd(cmd, args), session)


FILE_KIND = {"schedule": 1, "resv": 2, "exam": 3}


def _current_ver(s: Session, bld: str, room: int, kind: str) -> int:
    """재동기 FILE 이 실을 버전. 콘텐츠 변경(`_bump_ver`)과 달리 여기서는 올리지 않는다 —
    방의 유닛이 여러 개면 유닛마다 도는 FILE 이 매번 bump 하면 유닛 간 버전 핑퐁이 생긴다.
    행이 아직 없으면(콘텐츠가 한 번도 안 바뀜) 최초값 1로 만들어 쓴다."""
    rv = s.get(RoomVersion, (bld, room, kind))
    if rv is None:
        rv = RoomVersion(bld=bld, room=room, kind=kind, ver=1)
        s.add(rv)
    return rv.ver


def _enqueue_file(
    s: Session, info: RoomInfo, bld: str, room: int, unit: int, kind: str
) -> list[int]:
    """kind 전체 재동기 FILE. 유닛별로 (bld,room,unit,kind) 에 queued|dispatched FILE 이 있으면 그 id,
    없는 유닛만 새로 만든다 (v2 §8.3). 재동기는 방의 현재 버전을 그대로 싣는다 — bump 하지 않는다."""
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
    existing_by_unit = {
        r.unit: r.id for r in open_rows if json.loads(r.payload)["kind"] == FILE_KIND[kind]
    }
    missing = [u for u in units if u not in existing_by_unit]
    new_by_unit: dict[int, int] = {}
    if missing:
        new_ver = _current_ver(s, bld, room, kind)
        records = _records(bld, room, kind)
        C.build_file(FILE_KIND[kind], records, new_ver)  # 크기·kind 검증
        payload = json.dumps(
            {
                "kind": FILE_KIND[kind],
                "records": [jsonio.to_json(r, drop=("new_ver",)) for r in records],
            },
            ensure_ascii=False,
        )
        for u in missing:
            new_by_unit[u] = _insert(s, info, bld, room, u, "FILE", payload, new_ver)[0]
    return [existing_by_unit.get(u, new_by_unit.get(u)) for u in units]


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


def enqueue_file_replace(bld: str, room: int, kind: str, unit: int = 0) -> list[int]:
    """콘텐츠 변경 FILE (S2b §2.4): kind 버전 +1, 현재 RecordProvider 레코드로 FILE 을 새로 만들어
    유닛별 삽입. 재동기 FILE(enqueue_full_sync — bump 없음·queued 재사용)과 달리 기존 queued FILE 을
    재사용하지 않는다 — 임포트 직후 옛 내용의 FILE 이 나가고 새 내용이 영영 안 가는 것을 막는다.
    호출 측은 레코드가 커밋된 뒤에 부른다(RecordProvider 는 자기 세션으로 읽는다)."""
    info = _room(bld, room)
    file_kind = FILE_KIND[kind]
    with _Session() as s, s.begin():
        new_ver = _bump_ver(s, bld, room, kind)
        records = _records(bld, room, kind)
        C.build_file(file_kind, records, new_ver)  # 크기·kind 검증 — 실패면 롤백(버전도)
        payload = json.dumps(
            {"kind": file_kind, "records": [jsonio.to_json(r, drop=("new_ver",)) for r in records]},
            ensure_ascii=False,
        )
        ids = _insert(s, info, bld, room, unit, "FILE", payload, new_ver)
    if info.modem_id:
        _hub.notify(info.modem_id)
    return ids


def provision(mac: str, bld: str, room: int, unit: int) -> int:
    if unit not in (1, 2):
        raise ValidationError("unit 은 1 또는 2")
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


def reassign_queued(bld: str, rooms: list[int], modem_id: str | None) -> int:
    """건물에 모뎀이 없을 때 쌓인 queued job 을, 모뎀이 배정된 뒤 그 모뎀으로 재지정한다 (v2 §8.3)."""
    with _Session() as s, s.begin():
        n = s.execute(
            update(Outbox)
            .where(Outbox.bld == bld, Outbox.room.in_(rooms), Outbox.state == "queued")
            .values(modem_id=modem_id)
        ).rowcount
    if modem_id is not None:
        _hub.notify(modem_id)
    return n


def cancel(outbox_id: int) -> bool:
    """queued → cancelled. dispatched 는 커밋 후 모뎀Pi 에 cancel 을 보내고 job_result 를 기다린다 (spec §2.4)."""
    to_cancel: tuple[str, int] | None = None
    with _Session() as s, s.begin():
        row = s.get(Outbox, outbox_id)
        if row is None:
            return False
        if row.state == "queued":
            row.state = "cancelled"
            row.finished_at = utcnow()
            return True
        if row.state == "dispatched" and row.modem_id:
            to_cancel = (row.modem_id, row.id)
        else:
            return False
    _hub.cancel(*to_cancel)
    return True


_ACK_FIELDS = (
    "ack_status",
    "ack_detail",
    "attempts",
    "txn",
    "rssi",
    "snr",
    "sched_ver",
    "resv_ver",
    "exam_ver",
    "ident_ver",
    "batt_mv",
    "layout",
    "fw",
    "last_error",
)
_TS_FIELDS = (
    "sched_ver",
    "resv_ver",
    "exam_ver",
    "ident_ver",
    "batt_mv",
    "layout",
    "fw",
    "rssi",
    "snr",
)


def _status_row(s: Session, bld: str, room: int, unit: int, modem_id: str) -> TerminalStatus:
    ts = s.get(TerminalStatus, (bld, room, unit))
    if ts is None:
        ts = TerminalStatus(bld=bld, room=room, unit=unit)
        s.add(ts)
    ts.modem_id = modem_id
    ts.last_seen_at = utcnow()
    return ts


def _outbox_kind_pending(s: Session, bld: str, room: int, unit: int, kind: str) -> bool:
    """그 (bld,room,unit) 에 이 kind 를 이미 실어나를 queued|dispatched outbox 가 있는가.
    있으면 그 결과를 기다린다 — 파이프라인 편집 중 스푸리어스 FILE 재동기 방지 (F5)."""
    rows = s.scalars(
        select(Outbox).where(
            Outbox.bld == bld,
            Outbox.room == room,
            Outbox.unit == unit,
            Outbox.state.in_(("queued", "dispatched")),
        )
    ).all()
    return any(
        KIND_OF.get(r.type) == kind
        or (r.type == "FILE" and json.loads(r.payload)["kind"] == FILE_KIND[kind])
        for r in rows
    )


def _check_versions(
    s: Session,
    ts: TerminalStatus,
    bld: str,
    room: int,
    unit: int,
    msg: dict,
    *,
    gap_kind: str | None,
) -> list[str]:
    """ACK/STATUS 의 버전이 room_versions 와 다르거나(그 kind 가 GAP 이면) stale kind 목록을 낸다 (v2 §8.3).
    이미 그 kind 의 outbox 가 in-flight 면 결과를 기다리고 다시 큐잉하지 않는다.
    FILE 큐잉은 여기서 하지 않는다 — 별도 트랜잭션(`_queue_resync`)의 몫이다(I2: ACK 커밋을 지킨다)."""
    stale = []
    for kind, key in (("schedule", "sched_ver"), ("resv", "resv_ver"), ("exam", "exam_ver")):
        rv = s.get(RoomVersion, (bld, room, kind))
        if rv is None:
            continue
        if kind == gap_kind:
            stale.append(kind)  # GAP 은 노드가 관측한 불연속 — 억제하지 않는다
        elif msg.get(key) != rv.ver and not _outbox_kind_pending(s, bld, room, unit, kind):
            stale.append(kind)
    ts.sync_state = "resync" if stale else "synced"
    return stale


def _queue_resync(bld: str, room: int, unit: int, stale: list[str]) -> None:
    """stale kind 들의 FILE 재동기 큐잉, ACK/STATUS 커밋과 별도 트랜잭션 (v2 §8.3).
    실패해도 ACK/STATUS 는 이미 커밋된 채 남는다 — 하루 STATUS 가 다시 stale 을 발견해 재시도한다."""
    if not stale:
        return
    try:
        info = _topology.room(bld, room)
        if info is None:
            return
        with _Session() as s, s.begin():
            for kind in stale:
                _enqueue_file(s, info, bld, room, unit, kind)
        if info.modem_id:
            _hub.notify(info.modem_id)
    except Exception:
        log.exception("resync 큐잉 실패: %s%d#%d %s", bld, room, unit, stale)


def on_job_result(modem_id: str, msg: dict) -> None:
    stale: list[str] = []
    bld = room = unit = None
    with _Session() as s, s.begin():
        row = s.get(Outbox, int(msg["job_id"]))  # 계약 ⑦: 모뎀Pi가 TEXT 로 echo 할 수 있음
        if row is None or row.state in ("acked", "failed", "cancelled"):
            return  # 늦게 온·중복 보고
        if row.modem_id and row.modem_id != modem_id:
            log.warning("modem %s: job %s 는 %s 소유, 무시", modem_id, row.id, row.modem_id)
            return
        row.state = "acked" if msg.get("state") == "acked" else "failed"
        for k in _ACK_FIELDS:
            if k in msg:
                setattr(row, k, msg[k])
        row.finished_at = utcnow()
        if row.state != "acked":
            return
        ts = _status_row(s, row.bld, row.room, row.unit, modem_id)
        ts.last_ack_at = ts.last_seen_at
        for k in _TS_FIELDS:
            if k in msg:
                setattr(ts, k, msg[k])
        if row.type == "SET_ROOM":
            payload = json.loads(row.payload)
            ts.mac = payload["mac"]
            pd = s.get(PendingDevice, payload["mac"])
            if pd is not None:
                s.delete(pd)
        gap_kind = None
        # FILE 은 전체 교체 — GAP 을 재동기 트리거로 쓰지 않는다 (v2 §3.3 보강 예정)
        if msg.get("ack_status") == P.AckStatus.GAP and row.type != "FILE":
            gap_kind = KIND_OF.get(row.type)
        bld, room, unit = row.bld, row.room, row.unit
        stale = _check_versions(s, ts, bld, room, unit, msg, gap_kind=gap_kind)
    if bld is not None:
        _queue_resync(bld, room, unit, stale)


def on_uplink(modem_id: str, msg: dict) -> None:
    stale: list[str] = []
    bld = room = unit = None
    with _Session() as s, s.begin():
        if msg["kind"] == "HELLO":
            pd = s.get(PendingDevice, msg["mac"])
            if pd is None:
                pd = PendingDevice(mac=msg["mac"], first_seen_at=utcnow())
                s.add(pd)
            pd.modem_id, pd.fw, pd.batt_mv, pd.rssi = (
                modem_id,
                msg["fw"],
                msg["batt_mv"],
                msg["rssi"],
            )
            pd.last_seen_at = utcnow()
            return
        ts = _status_row(s, msg["bld"], msg["room"], msg["unit"], modem_id)
        ts.last_status_at = ts.last_seen_at
        for k in _TS_FIELDS:
            if k in msg:
                setattr(ts, k, msg[k])
        ts.uptime_h = msg.get("uptime_h")
        flags = msg.get("flags", 0)
        ts.clock_stale = bool(flags & P.StatusFlag.CLOCK_STALE)
        ts.low_batt = bool(flags & P.StatusFlag.LOW_BATT)
        bld, room, unit = msg["bld"], msg["room"], msg["unit"]
        stale = _check_versions(s, ts, bld, room, unit, msg, gap_kind=None)
    if bld is not None:
        _queue_resync(bld, room, unit, stale)


# ---------- 모뎀 레지스트리 ----------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register_modem(modem_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with _Session() as s, s.begin():
        if s.get(Modem, modem_id) is not None:
            raise ValidationError(f"modem {modem_id} 이미 있음")
        s.add(Modem(modem_id=modem_id, token_hash=_hash(token)))
    return token


def rotate_token(modem_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with _Session() as s, s.begin():
        m = s.get(Modem, modem_id)
        if m is None:
            raise NotFound(modem_id)
        m.token_hash = _hash(token)
    return token


def verify_token(modem_id: str, token: str) -> bool:
    with _Session() as s:
        m = s.get(Modem, modem_id)
        return m is not None and secrets.compare_digest(m.token_hash, _hash(token))


def touch_modem(
    modem_id: str, *, connected: bool, agent_ver: str | None = None, modem_fw: str | None = None
) -> None:
    with _Session() as s, s.begin():
        m = s.get(Modem, modem_id)
        if m is None:
            return
        m.connected = connected
        m.last_seen_at = utcnow()
        if agent_ver is not None:
            m.agent_ver = agent_ver
        if modem_fw is not None:
            m.modem_fw = modem_fw


def reset_connections() -> int:
    """기동 시 호출. 이전 프로세스가 죽으며 남긴 connected=True 를 정리한다(로드맵 §4.2)."""
    with _Session() as s, s.begin():
        stale = s.scalars(select(Modem).where(Modem.connected.is_(True))).all()
        now = utcnow()
        for m in stale:
            m.connected = False
            m.last_seen_at = now
        return len(stale)


def get_modems() -> list[Modem]:
    with _Session() as s:
        return list(s.scalars(select(Modem).order_by(Modem.modem_id)))


def get_status(bld: str | None = None, room: int | None = None) -> list[TerminalStatus]:
    q = select(TerminalStatus).order_by(
        TerminalStatus.bld, TerminalStatus.room, TerminalStatus.unit
    )
    if bld:
        q = q.where(TerminalStatus.bld == bld)
    if room is not None:
        q = q.where(TerminalStatus.room == room)
    with _Session() as s:
        return list(s.scalars(q))


def get_pending_devices() -> list[PendingDevice]:
    with _Session() as s:
        return list(s.scalars(select(PendingDevice).order_by(PendingDevice.last_seen_at.desc())))


def sweep_offline(now: dt.datetime | None = None) -> int:
    """24 h 이상 안 붙은 모뎀의 dispatched → failed(modem_offline) (로드맵 §4.2)."""
    now = now or utcnow()
    cutoff = now - dt.timedelta(hours=24)
    n = 0
    with _Session() as s, s.begin():
        dead = s.scalars(
            select(Modem).where(Modem.connected.is_(False), Modem.last_seen_at < cutoff)
        ).all()
        for m in dead:
            rows = s.scalars(
                select(Outbox).where(Outbox.modem_id == m.modem_id, Outbox.state == "dispatched")
            ).all()
            for r in rows:
                r.state, r.last_error, r.finished_at = "failed", "modem_offline", now
                n += 1
    return n
