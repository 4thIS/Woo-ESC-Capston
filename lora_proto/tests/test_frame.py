import pytest

from lora_proto import proto as P
from lora_proto.codec import FrameError, Header, crc8, decode_frame, encode_frame


def test_header_layout_matches_spec_3_1():
    h = Header(type=P.Type.SLOT_SET, bld=ord("E"), room=301, unit=1, txn=7, flags=P.FLAG_ACK_REQ)
    frame = encode_frame(h, b"\x03\x01")
    assert frame[0] == 0x21  # ver 2 <<4 | ACK_REQ
    assert frame[1] == P.NET_ID
    assert frame[2] == P.Type.SLOT_SET
    assert frame[3] == ord("E")
    assert frame[4:6] == (301).to_bytes(2, "big")
    assert frame[6] == 1
    assert frame[7] == 7
    assert frame[8] == 2  # LEN
    assert frame[9:11] == b"\x03\x01"
    assert frame[11] == crc8(frame[:11])
    assert len(frame) == P.HEADER_LEN + 2 + 1


def test_roundtrip():
    h = Header(
        type=P.Type.TIME, bld=P.BLD_ALL, room=P.ROOM_ALL, unit=0, txn=0, flags=P.FLAG_BROADCAST
    )
    payload = bytes(range(245))
    h2, p2 = decode_frame(encode_frame(h, payload))
    assert h2 == h and p2 == payload


def test_payload_too_long_rejected():
    h = Header(type=P.Type.TIME, bld=P.BLD_ALL, room=P.ROOM_ALL, unit=0, txn=0)
    with pytest.raises(FrameError):
        encode_frame(h, bytes(246))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f[:-1] + bytes([f[-1] ^ 0xFF]),  # CRC 깨짐
        lambda f: f[:1] + bytes([0x00]) + f[2:],  # NET_ID 불일치
        lambda f: bytes([0x30]) + f[1:],  # 프로토콜 버전 3
        lambda f: f[:8] + bytes([9]) + f[9:],  # LEN 이 실제보다 큼
        lambda f: f[:5],  # 헤더보다 짧음
    ],
)
def test_bad_frames_raise(mutate):
    h = Header(type=P.Type.SLOT_DEL, bld=ord("A"), room=1, unit=2, txn=255)
    f = encode_frame(h, b"\x01\x02\x03")
    with pytest.raises(FrameError):
        decode_frame(mutate(f))


def test_ack_matching_uses_addr_and_txn_only():
    req = Header(type=P.Type.SLOT_SET, bld=ord("E"), room=301, unit=1, txn=7, flags=P.FLAG_ACK_REQ)
    ack = Header(type=P.Type.ACK, bld=ord("E"), room=301, unit=1, txn=7)
    assert req.matches_ack(ack)
    assert not req.matches_ack(Header(type=P.Type.ACK, bld=ord("E"), room=301, unit=1, txn=8))
    assert not req.matches_ack(Header(type=P.Type.STATUS, bld=ord("E"), room=301, unit=1, txn=7))
