"""test_vectors.json 생성기. Python codec 이 만든 프레임을 C++ Unity 테스트가 바이트 단위로 재검증한다.
실행: uv run python -m tools.gen_vectors  (lora_proto/ 에서)"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from lora_proto import codec as C
from lora_proto import proto as P

OUT = Path(__file__).resolve().parents[1] / "test_vectors.json"
_CLASSES = {
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


def to_json(obj: object) -> dict:
    """dataclass → JSON dict. bytes 는 hex 문자열, 중첩 dataclass 는 재귀."""
    out = {}
    for f in dataclasses.fields(obj):
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


def from_json(type_: int, d: dict) -> object:
    cls = _CLASSES[type_]
    kw = {}
    for f in dataclasses.fields(cls):
        v = d[f.name]
        if f.name == "ack":
            kw[f.name] = from_json(P.Type.ACK, v)
        elif f.name in ("mac", "args", "data"):
            kw[f.name] = bytes.fromhex(v)
        else:
            kw[f.name] = v
    return cls(**kw)


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def _vec(name: str, h: C.Header, payload: object) -> dict:
    frame = C.encode_frame(h, C.encode_payload(payload))
    return {
        "name": name,
        "header": {
            "type": int(h.type),
            "bld": h.bld,
            "room": h.room,
            "unit": h.unit,
            "txn": h.txn,
            "flags": h.flags,
        },
        "payload": to_json(payload),
        "frame_hex": _hex(frame),
    }


E, A = ord("E"), ord("A")
MAC = bytes.fromhex("a0b1c2d3e4f5")


def build() -> dict:
    T = P.Type
    slot = C.SlotSet(
        3, 3, 9, 0, 10, 50, P.SlotType.CLASS, "임베디드SW", "정필성"
    )  # 14 B (SUBJ_MAX 20)
    slot_max = C.SlotSet(255, 7, 23, 59, 23, 59, P.SlotType.RENTAL, "가" * 6 + "ab", "가" * 4)
    resv = C.ResvSet(2, 0x0102, 2026, 11, 19, 13, 0, 15, 0, P.SlotType.RENTAL, "경진대회", "산학처")
    exam = C.ExamSet(4, 7, 2026, 10, 20, 2026, 10, 24)
    ack = C.Ack(P.AckStatus.OK, 0, 3987, 12, 3, 1, 1, 20, P.Layout.CLASS)
    big_records = [
        C.SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(12)
    ]  # 40 B × 12 = 480 B → 3 청크
    fb, fd0, _fd1, fd2, fe = C.build_file(P.FileKind.SCHEDULE, big_records, new_ver=9)
    assert fd2.seq == 2 and len(fd0.data) == P.FILE_CHUNK_MAX

    def H(t, bld=E, room=301, unit=1, txn=7, flags=P.FLAG_ACK_REQ):
        return C.Header(type=t, bld=bld, room=room, unit=unit, txn=txn, flags=flags)

    vectors = [
        _vec(
            "time_broadcast",
            H(T.TIME, P.BLD_ALL, P.ROOM_ALL, 0, 0, P.FLAG_BROADCAST | P.FLAG_WAKE_SENT),
            C.Time(1_757_400_000, P.TimeFlag.REQUEST_STATUS),
        ),
        _vec(
            "time_targeted_resync",
            H(T.TIME, flags=P.FLAG_WAKE_SENT, txn=0),
            C.Time(1_757_403_600, 0),
        ),
        _vec("slot_set_basic", H(T.SLOT_SET), slot),
        _vec("slot_set_max_strings_ver255", H(T.SLOT_SET, txn=255), slot_max),
        _vec(
            "slot_set_unit0_all_units",
            H(T.SLOT_SET, unit=0, txn=1),
            C.SlotSet(1, 1, 9, 0, 10, 0, 1, "s", "p"),
        ),
        _vec("slot_del", H(T.SLOT_DEL, txn=8), C.SlotDel(4, 3, 9, 0)),
        _vec("day_clear", H(T.DAY_CLEAR, txn=9), C.DayClear(5, 3)),
        _vec("resv_set_rental", H(T.RESV_SET, txn=10), resv),
        _vec(
            "resv_set_ascii",
            H(T.RESV_SET, A, 1, 2, 11),
            C.ResvSet(1, 1, 2026, 1, 1, 0, 0, 23, 59, P.SlotType.CANCELLED, "abc", "xy"),
        ),
        _vec("resv_del", H(T.RESV_DEL, txn=12), C.ResvDel(3, 0x0102)),
        _vec("exam_set", H(T.EXAM_SET, txn=13), exam),
        _vec("exam_del", H(T.EXAM_DEL, txn=14), C.ExamDel(5, 7)),
        _vec("file_begin_schedule_3chunks", H(T.FILE_BEGIN, txn=15), fb),
        _vec("file_data_seq0_full_200B", H(T.FILE_DATA, txn=16), fd0),
        _vec("file_data_seq2_tail", H(T.FILE_DATA, txn=18), fd2),
        _vec("file_end", H(T.FILE_END, txn=19), fe),
        _vec(
            "file_begin_empty_resv", H(T.FILE_BEGIN, txn=20), C.FileBegin(1, P.FileKind.RESV, 0, 0)
        ),
        _vec("cmd_reboot", H(T.CMD, txn=21), C.Cmd(P.Cmd.REBOOT)),
        _vec(
            "cmd_test_render_layout7",
            H(T.CMD, txn=22),
            C.Cmd(P.Cmd.TEST_RENDER, bytes([P.Layout.RENTAL])),
        ),
        _vec(
            "cmd_set_param_status_hour",
            H(T.CMD, txn=23),
            C.Cmd(P.Cmd.SET_PARAM, bytes([1]) + (18).to_bytes(4, "big")),
        ),
        _vec(
            "set_room_provision",
            H(T.SET_ROOM, P.BLD_UNPROVISIONED, 0, 0, 24),
            C.SetRoom(1, MAC, E, 301, 2),
        ),
        _vec("ack_ok", H(T.ACK, txn=7, flags=0), ack),
        _vec(
            "ack_gap",
            H(T.ACK, txn=8, flags=0),
            dataclasses.replace(ack, status=P.AckStatus.GAP, sched_ver=11),
        ),
        _vec(
            "ack_file_missing_seq3",
            H(T.ACK, txn=16, flags=0),
            dataclasses.replace(ack, status=P.AckStatus.FILE_MISSING, detail=3),
        ),
        _vec(
            "status_daily",
            H(T.STATUS, txn=0, flags=0),
            C.Status(ack, -97, -6, P.StatusFlag.LOW_BATT, 300),
        ),
        _vec(
            "status_clock_stale_positive_snr",
            H(T.STATUS, txn=0, flags=0),
            C.Status(ack, -60, 38, P.StatusFlag.CLOCK_STALE, 0),
        ),
        _vec(
            "hello_unprovisioned",
            H(T.HELLO, P.BLD_UNPROVISIONED, 0, 0, 0, 0),
            C.Hello(MAC, 20, 4100),
        ),
    ]
    return {"proto_ver": P.PROTO_VER, "net_id": P.NET_ID, "vectors": vectors}


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(build()['vectors'])} vectors)")
    sys.exit(0)
