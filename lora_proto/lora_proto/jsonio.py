"""codec dataclass ↔ JSON dict 변환기 — 메인Pi(`job.payload`)·모뎀Pi(preprocess)·테스트 벡터가 공유하는 유일한 변환 규칙.

규칙 (로드맵 §4.2 "메시지 인코딩 규칙"):
- 키는 dataclass 필드명 그대로.
- bytes 필드(`mac`, `args`, `data`)는 소문자 hex 문자열, 구분자 없음.
- 중첩 dataclass(`Status.ack`)는 재귀.
- IntEnum 은 int 로.
- `new_ver` 는 포함한다. FILE 레코드처럼 NEW_VER 가 없는 문맥에서는 호출자가 `drop=("new_ver",)` 로 뺀다.
"""

from __future__ import annotations

import dataclasses

from . import codec as C
from . import proto as P

CLASSES: dict[int, type] = {
    P.Type.TIME: C.Time,
    P.Type.SLOT_SET: C.SlotSet,
    P.Type.SLOT_DEL: C.SlotDel,
    P.Type.DAY_CLEAR: C.DayClear,
    P.Type.RESV_SET: C.ResvSet,
    P.Type.RESV_DEL: C.ResvDel,
    P.Type.EXAM_SET: C.ExamSet,
    P.Type.EXAM_DEL: C.ExamDel,
    P.Type.FILE_BEGIN: C.FileBegin,
    P.Type.FILE_DATA: C.FileData,
    P.Type.FILE_END: C.FileEnd,
    P.Type.CMD: C.Cmd,
    P.Type.SET_ROOM: C.SetRoom,
    P.Type.ACK: C.Ack,
    P.Type.STATUS: C.Status,
    P.Type.HELLO: C.Hello,
}
_BYTES_FIELDS = frozenset({"mac", "args", "data"})


def to_json(obj: object, *, drop: tuple[str, ...] = ()) -> dict:
    """dataclass → JSON dict. `drop` 에 든 필드는 뺀다 (예: FILE 레코드의 `new_ver`)."""
    out = {}
    for f in dataclasses.fields(obj):
        if f.name in drop:
            continue
        v = getattr(obj, f.name)
        if isinstance(v, bytes):
            out[f.name] = v.hex()
        elif dataclasses.is_dataclass(v):
            out[f.name] = to_json(v)
        elif isinstance(v, str):
            out[f.name] = v
        else:
            out[f.name] = int(v)
    return out


def from_json(type_: int, d: dict, **override: object) -> object:
    """JSON dict → dataclass. dict 에 없는 필드는 `override` 로 준다 (예: `new_ver=job.new_ver`).

    dict 에도 override 에도 없는 필드는 `FrameError` 대신 `KeyError` — 호출자가 계약 위반으로 다룬다.
    """
    cls = CLASSES[type_]
    kw: dict[str, object] = {}
    for f in dataclasses.fields(cls):
        if f.name in override:
            kw[f.name] = override[f.name]
            continue
        v = d[f.name]
        if f.name == "ack":
            kw[f.name] = from_json(P.Type.ACK, v)
        elif f.name in _BYTES_FIELDS:
            kw[f.name] = bytes.fromhex(v)
        else:
            kw[f.name] = v
    return cls(**kw)
