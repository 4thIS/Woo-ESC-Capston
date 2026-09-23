"""jobs 행 → 공중에 실제로 나갈 단위 목록. 프레임 바이트는 worker 가 만든다 (S6 spec §4.2)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from lora_proto import codec as C
from lora_proto import jsonio
from lora_proto import proto as P

from modempi.store import Job

# FILE 종류별 레코드 타입. 레코드 dict 에는 new_ver 키가 없어 job.new_ver 를 주입한다(로드맵 §4.2).
_REC_TYPE = {
    P.FileKind.SCHEDULE: P.Type.SLOT_SET,
    P.FileKind.RESV: P.Type.RESV_SET,
    P.FileKind.EXAM: P.Type.EXAM_SET,
}


class PreprocessError(ValueError):
    """이 작업은 보낼 수 없다. str(e) 가 그대로 jobs.last_error 가 된다."""


@dataclass(frozen=True)
class Unit:
    """송신 1회 단위. `bld` 는 헤더용 ASCII 정수 — 계약 ⑦ 의 한 글자 문자열과 표현이 다르다."""

    bld: int
    room: int
    unit: int
    type: int
    payload_obj: object
    wake: bool
    ack_ms: int
    flags: int


def is_file_session(units: list[Unit]) -> bool:
    """FILE 세션이면 True — BEGIN/DATA/END 를 한 창 안에서 이어 보내야 한다."""
    return bool(units) and units[0].type == P.Type.FILE_BEGIN


def preprocess(job: Job, *, clock: Callable[[], float] = time.time) -> list[Unit]:
    """작업 행 하나를 보낼 단위 목록으로. 보낼 수 없는 행은 `PreprocessError`."""
    try:
        payload = json.loads(job.payload)
    except ValueError as e:
        raise PreprocessError(f"bad_payload: {e}") from e

    if job.type == "TIME":
        return [_time_unit(job, payload, clock)]
    if job.unit == 0:
        raise PreprocessError("unit0")
    if job.type == "FILE":
        return _file_units(job, payload)
    return [_plain_unit(job, payload)]


def _addr(job: Job) -> tuple[int, int, int]:
    """계약 ⑦ 의 한 글자 bld 를 헤더용 ASCII 정수로. 이 변환은 이 파일에서만 한다."""
    return ord(job.bld), job.room, job.unit


def _time_unit(job: Job, payload: dict, clock: Callable[[], float]) -> Unit:
    flags = int(payload.get("flags", 0))
    obj = C.Time(int(clock()), flags)  # 쌓여 있던 행이 옛 시각을 뿌리지 않게 지금 시각으로
    if job.bld == "":
        return Unit(P.BLD_ALL, P.ROOM_ALL, 0, P.Type.TIME, obj, True, 0, P.FLAG_BROADCAST)
    bld, room, unit = _addr(job)
    return Unit(bld, room, unit, P.Type.TIME, obj, True, 0, 0)


def _plain_unit(job: Job, payload: dict) -> Unit:
    try:
        type_ = P.Type[job.type]
        obj = jsonio.from_json(type_, payload, new_ver=job.new_ver)
    except (KeyError, ValueError, TypeError) as e:
        raise PreprocessError(f"bad_payload: {e}") from e
    bld, room, unit = _addr(job)
    return Unit(bld, room, unit, type_, obj, True, 3000, P.FLAG_ACK_REQ)


def _file_units(job: Job, payload: dict) -> list[Unit]:
    try:
        kind = int(payload["kind"])
        rec_type = _REC_TYPE[P.FileKind(kind)]
        records = [jsonio.from_json(rec_type, r, new_ver=job.new_ver) for r in payload["records"]]
        parts = C.build_file(kind, records, job.new_ver)
    except (KeyError, ValueError, TypeError, C.FrameError) as e:
        raise PreprocessError(f"bad_payload: {e}") from e
    bld, room, unit = _addr(job)
    return [
        Unit(bld, room, unit, C.type_of(p), p, i == 0, 3000, P.FLAG_ACK_REQ)
        for i, p in enumerate(parts)
    ]
