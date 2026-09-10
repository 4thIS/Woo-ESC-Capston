import pytest

from lora_proto import proto as P
from lora_proto.codec import (
    Ack,
    Cmd,
    DayClear,
    ExamDel,
    ExamSet,
    FrameError,
    Hello,
    ResvDel,
    ResvSet,
    SetRoom,
    SlotDel,
    SlotSet,
    Status,
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


def test_resv_set_layout_and_roundtrip():
    r = ResvSet(
        new_ver=2,
        resv_id=0x0102,
        year=2026,
        month=11,
        day=19,
        s_h=13,
        s_m=0,
        e_h=15,
        e_m=0,
        type=P.SlotType.RENTAL,
        subject="경진대회",
        professor="산학처",
    )
    b = encode_payload(r)
    assert b[:11] == bytes([2, 0x01, 0x02, 26, 11, 19, 13, 0, 15, 0, 6])
    assert decode_payload(P.Type.RESV_SET, b) == r


def test_resv_del_exam_set_exam_del():
    assert encode_payload(ResvDel(9, 0xBEEF)) == bytes([9, 0xBE, 0xEF])
    assert decode_payload(P.Type.RESV_DEL, bytes([9, 0xBE, 0xEF])) == ResvDel(9, 0xBEEF)
    e = ExamSet(4, 7, 2026, 10, 20, 2026, 10, 24)
    assert encode_payload(e) == bytes([4, 0, 7, 26, 10, 20, 26, 10, 24])
    assert decode_payload(P.Type.EXAM_SET, encode_payload(e)) == e
    assert decode_payload(P.Type.EXAM_DEL, bytes([4, 0, 7])) == ExamDel(4, 7)


@pytest.mark.parametrize(
    "bad",
    [
        {"year": 1999},
        {"year": 2256},
        {"month": 13},
        {"day": 0},
        {"day": 32},
    ],
)
def test_resv_date_ranges(bad):
    base = {
        "new_ver": 1,
        "resv_id": 1,
        "year": 2026,
        "month": 1,
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
        encode_payload(ResvSet(**{**base, **bad}))


def test_cmd_layouts():
    assert encode_payload(Cmd(P.Cmd.REBOOT)) == bytes([2])
    assert encode_payload(Cmd(P.Cmd.TEST_RENDER, bytes([5]))) == bytes([1, 5])
    sp = Cmd(P.Cmd.SET_PARAM, bytes([1]) + (300).to_bytes(4, "big"))
    assert decode_payload(P.Type.CMD, encode_payload(sp)) == sp
    with pytest.raises(FrameError):
        encode_payload(Cmd(0x07))


def test_set_room_layout():
    mac = bytes.fromhex("aabbccddeeff")
    s = SetRoom(new_ver=1, mac=mac, bld=ord("E"), room=301, unit=2)
    assert encode_payload(s) == bytes([1]) + mac + bytes([0x45, 0x01, 0x2D, 2])
    assert decode_payload(P.Type.SET_ROOM, encode_payload(s)) == s
    with pytest.raises(FrameError):
        encode_payload(SetRoom(1, b"\x00" * 5, 0x45, 1, 1))


def test_ack_status_hello_layouts():
    a = Ack(
        status=P.AckStatus.GAP,
        detail=0,
        batt_mv=3987,
        sched_ver=12,
        resv_ver=3,
        exam_ver=1,
        ident_ver=1,
        fw=20,
        layout=P.Layout.CLASS,
    )
    ab = encode_payload(a)
    assert ab == bytes([4, 0, 0x0F, 0x93, 12, 3, 1, 1, 20, 1])
    assert decode_payload(P.Type.ACK, ab) == a

    st = Status(ack=a, rssi_last=-97, snr_last_x4=-6, flags=P.StatusFlag.LOW_BATT, uptime_h=300)
    sb = encode_payload(st)
    assert sb == ab + bytes([0x9F, 0xFA, 0x04, 0x01, 0x2C])
    assert decode_payload(P.Type.STATUS, sb) == st

    h = Hello(mac=bytes.fromhex("0011223344ff"), fw=20, batt_mv=4100)
    assert encode_payload(h) == bytes.fromhex("0011223344ff") + bytes([20, 0x10, 0x04])
    assert decode_payload(P.Type.HELLO, encode_payload(h)) == h
