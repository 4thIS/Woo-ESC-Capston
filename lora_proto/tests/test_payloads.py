import pytest

from lora_proto import proto as P
from lora_proto.codec import (
    DayClear,
    FrameError,
    SlotDel,
    SlotSet,
    Time,
    decode_payload,
    encode_payload,
)


def test_time_layout():
    b = encode_payload(Time(epoch=1_757_400_000, flags=P.TimeFlag.REQUEST_STATUS))
    assert b == (1_757_400_000).to_bytes(4, "big") + b"\x01"
    assert decode_payload(P.Type.TIME, b) == Time(epoch=1_757_400_000, flags=1)


def test_slot_set_layout_and_roundtrip():
    s = SlotSet(
        new_ver=3,
        day=3,
        s_h=9,
        s_m=0,
        e_h=10,
        e_m=50,
        type=P.SlotType.CLASS,
        subject="가" * 6 + "ab",
        professor="정필성",
    )
    b = encode_payload(s)
    subj = ("가" * 6 + "ab").encode()
    prof = "정필성".encode()
    assert b == bytes([3, 3, 9, 0, 10, 50, 1, len(subj)]) + subj + bytes([len(prof)]) + prof
    assert decode_payload(P.Type.SLOT_SET, b) == s


def test_slot_set_string_limits():
    ok = SlotSet(1, 1, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4)  # 20 B, 12 B
    encode_payload(ok)
    with pytest.raises(FrameError):
        encode_payload(SlotSet(1, 1, 9, 0, 10, 0, 1, "가" * 7, "x"))  # 21 B
    with pytest.raises(FrameError):
        encode_payload(SlotSet(1, 1, 9, 0, 10, 0, 1, "x", "가" * 5))  # 15 B


@pytest.mark.parametrize(
    "bad",
    [
        {"day": 0},
        {"day": 8},
        {"s_h": 24},
        {"s_m": 60},
        {"e_h": 24},
        {"new_ver": 256},
        {"type": 0},
        {"type": 7},
    ],
)
def test_slot_set_field_ranges(bad):
    base = {
        "new_ver": 1,
        "day": 1,
        "s_h": 9,
        "s_m": 0,
        "e_h": 10,
        "e_m": 0,
        "type": 1,
        "subject": "s",
        "professor": "p",
    }
    with pytest.raises(FrameError):
        encode_payload(SlotSet(**{**base, **bad}))


def test_slot_del_and_day_clear():
    assert encode_payload(SlotDel(5, 2, 13, 30)) == bytes([5, 2, 13, 30])
    assert decode_payload(P.Type.SLOT_DEL, bytes([5, 2, 13, 30])) == SlotDel(5, 2, 13, 30)
    assert encode_payload(DayClear(6, 7)) == bytes([6, 7])
    assert decode_payload(P.Type.DAY_CLEAR, bytes([6, 7])) == DayClear(6, 7)


def test_decode_truncated_payload_raises():
    with pytest.raises(FrameError):
        decode_payload(
            P.Type.SLOT_SET, bytes([3, 3, 9, 0, 10, 50, 1, 5, 0x41])
        )  # subjLen 5 인데 1 B
    with pytest.raises(FrameError):
        decode_payload(P.Type.TIME, b"\x00\x00\x00")


def test_decode_trailing_bytes_raises():
    with pytest.raises(FrameError):
        decode_payload(P.Type.DAY_CLEAR, bytes([6, 7, 9]))
