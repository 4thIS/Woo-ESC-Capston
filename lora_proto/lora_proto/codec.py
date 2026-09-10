"""v2 §3 공중 프레임 codec — 바이트 변환만 한다. 재시도·TXN 배정·큐는 여기 없다(S6)."""

from __future__ import annotations

from dataclasses import dataclass

from . import proto as P


class FrameError(ValueError):
    """프레임/페이로드가 규격에 맞지 않음. 메시지에 이유를 담는다."""


# ---------- CRC ----------


def _make_crc8_table() -> list[int]:
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
        table.append(c)
    return table


_CRC8 = _make_crc8_table()


def crc8(data: bytes) -> int:
    """CRC-8, poly 0x07, init 0x00, no reflect, xorout 0 (v2 §3.1)."""
    c = 0
    for b in data:
        c = _CRC8[c ^ b]
    return c


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE, poly 0x1021, init 0xFFFF (v2 §3.3 FILE_END)."""
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


# ---------- 헤더 · 프레임 ----------


@dataclass(frozen=True)
class Header:
    type: int
    bld: int  # ASCII 코드 ('E'=0x45) 또는 BLD_UNPROVISIONED/BLD_ALL
    room: int  # 1..9999 또는 ROOM_ALL
    unit: int  # 0 전체 / 1 앞문 / 2 뒷문
    txn: int  # 1..255, 업링크·브로드캐스트는 0
    flags: int = 0
    net_id: int = P.NET_ID
    ver: int = P.PROTO_VER

    def matches_ack(self, other: Header) -> bool:
        """v2 §4.4: ACK 는 [NET_ID, TYPE==ACK, BLD/ROOM/UNIT/TXN] 이 송신 헤더와 같아야 한다."""
        return (
            other.type == P.Type.ACK
            and other.net_id == self.net_id
            and (other.bld, other.room, other.unit, other.txn)
            == (self.bld, self.room, self.unit, self.txn)
        )


def _check_u8(name: str, v: int) -> None:
    if not 0 <= v <= 0xFF:
        raise FrameError(f"{name}={v} 는 u8 범위 밖")


def encode_frame(h: Header, payload: bytes) -> bytes:
    if len(payload) > P.MAX_PAYLOAD:
        raise FrameError(f"payload {len(payload)} B > {P.MAX_PAYLOAD}")
    for name, v in (
        ("bld", h.bld),
        ("unit", h.unit),
        ("txn", h.txn),
        ("type", h.type),
        ("net_id", h.net_id),
    ):
        _check_u8(name, v)
    if not 0 <= h.room <= 0xFFFF:
        raise FrameError(f"room={h.room} 는 u16 범위 밖")
    if h.flags & ~0x0F:
        raise FrameError(f"flags={h.flags:#x} 는 4비트 초과")
    head = bytes(
        [
            (h.ver << 4) | h.flags,
            h.net_id,
            h.type,
            h.bld,
            (h.room >> 8) & 0xFF,
            h.room & 0xFF,
            h.unit,
            h.txn,
            len(payload),
        ]
    )
    body = head + payload
    return body + bytes([crc8(body)])


def decode_frame(buf: bytes, *, net_id: int = P.NET_ID) -> tuple[Header, bytes]:
    if len(buf) < P.HEADER_LEN + 1:
        raise FrameError(f"프레임 {len(buf)} B 는 헤더+CRC 최소 {P.HEADER_LEN + 1} B 미만")
    ver = buf[0] >> 4
    if ver != P.PROTO_VER:
        raise FrameError(f"프로토콜 버전 {ver} != {P.PROTO_VER}")
    if buf[1] != net_id:
        raise FrameError(f"NET_ID {buf[1]:#x} != {net_id:#x}")
    ln = buf[8]
    if len(buf) != P.HEADER_LEN + ln + 1:
        raise FrameError(f"LEN={ln} 이지만 실제 길이 {len(buf)}")
    if crc8(buf[:-1]) != buf[-1]:
        raise FrameError("CRC8 불일치")
    h = Header(
        type=buf[2],
        bld=buf[3],
        room=(buf[4] << 8) | buf[5],
        unit=buf[6],
        txn=buf[7],
        flags=buf[0] & 0x0F,
        net_id=buf[1],
        ver=ver,
    )
    return h, bytes(buf[P.HEADER_LEN : P.HEADER_LEN + ln])
