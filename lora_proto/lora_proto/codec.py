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


# ---------- 페이로드 공통 ----------


def _u8(name: str, v: int, lo: int = 0, hi: int = 255) -> int:
    if not lo <= v <= hi:
        raise FrameError(f"{name}={v} 는 {lo}..{hi} 밖")
    return v


def _hm(h: int, m: int, name: str) -> tuple[int, int]:
    return _u8(f"{name}H", h, 0, 23), _u8(f"{name}M", m, 0, 59)


def _pack_str(s: str, max_len: int, name: str) -> bytes:
    b = s.encode("utf-8")
    if len(b) > max_len:
        raise FrameError(f"{name} {len(b)} B > {max_len} B (잘라내기는 상위 계층 책임)")
    return bytes([len(b)]) + b


class _Reader:
    """페이로드 바이트를 앞에서부터 읽는다. 부족하면 FrameError."""

    def __init__(self, b: bytes, what: str):
        self.b, self.i, self.what = b, 0, what

    def u8(self) -> int:
        if self.i >= len(self.b):
            raise FrameError(f"{self.what}: {self.i} 바이트에서 잘림")
        v = self.b[self.i]
        self.i += 1
        return v

    def u16(self) -> int:
        return (self.u8() << 8) | self.u8()

    def u32(self) -> int:
        return (self.u16() << 16) | self.u16()

    def raw(self, n: int) -> bytes:
        if self.i + n > len(self.b):
            raise FrameError(f"{self.what}: {n} B 필요, {len(self.b) - self.i} B 남음")
        v = self.b[self.i : self.i + n]
        self.i += n
        return bytes(v)

    def s(self, max_len: int, name: str) -> str:
        n = self.u8()
        if n > max_len:
            raise FrameError(f"{self.what}.{name} 길이 {n} > {max_len}")
        try:
            return self.raw(n).decode("utf-8")
        except UnicodeDecodeError as e:
            raise FrameError(f"{self.what}.{name} UTF-8 아님") from e

    def done(self) -> None:
        if self.i != len(self.b):
            raise FrameError(f"{self.what}: 뒤에 {len(self.b) - self.i} B 남음")


# ---------- §3.3 페이로드 dataclass ----------


@dataclass(frozen=True)
class Time:
    epoch: int
    flags: int = 0


@dataclass(frozen=True)
class SlotSet:
    new_ver: int
    day: int
    s_h: int
    s_m: int
    e_h: int
    e_m: int
    type: int
    subject: str
    professor: str


@dataclass(frozen=True)
class SlotDel:
    new_ver: int
    day: int
    s_h: int
    s_m: int


@dataclass(frozen=True)
class DayClear:
    new_ver: int
    day: int


def _slot_body(s: SlotSet) -> bytes:
    """SLOT_SET 의 NEW_VER 뒤 본문. FILE 레코드에서도 재사용(Task 6)."""
    sh, sm = _hm(s.s_h, s.s_m, "s")
    eh, em = _hm(s.e_h, s.e_m, "e")
    return (
        bytes(
            [
                _u8("day", s.day, 1, 7),
                sh,
                sm,
                eh,
                em,
                _u8("type", s.type, 1, 6),
            ]
        )
        + _pack_str(s.subject, P.SUBJ_MAX, "subject")
        + _pack_str(s.professor, P.PROF_MAX, "professor")
    )


def _slot_read(r: _Reader, new_ver: int) -> SlotSet:
    day = r.u8()
    sh = r.u8()
    sm = r.u8()
    eh = r.u8()
    em = r.u8()
    t = r.u8()
    subj = r.s(P.SUBJ_MAX, "subject")
    prof = r.s(P.PROF_MAX, "professor")
    return SlotSet(
        new_ver,
        _u8("day", day, 1, 7),
        *_hm(sh, sm, "s"),
        *_hm(eh, em, "e"),
        _u8("type", t, 1, 6),
        subj,
        prof,
    )


_ENCODERS: dict[type, tuple[int, object]] = {}
_DECODERS: dict[int, object] = {}


def _register(t: int, cls: type, enc, dec) -> None:
    _ENCODERS[cls] = (t, enc)
    _DECODERS[t] = dec


def _enc_time(p: Time) -> bytes:
    if not 0 <= p.epoch <= 0xFFFFFFFF:
        raise FrameError(f"epoch={p.epoch} 는 u32 밖")
    return p.epoch.to_bytes(4, "big") + bytes([_u8("flags", p.flags)])


def _dec_time(b: bytes) -> Time:
    r = _Reader(b, "TIME")
    v = Time(r.u32(), r.u8())
    r.done()
    return v


def _dec_slot_set(b: bytes) -> SlotSet:
    r = _Reader(b, "SLOT_SET")
    v = _slot_read(r, r.u8())
    r.done()
    return v


def _enc_slot_del(p: SlotDel) -> bytes:
    sh, sm = _hm(p.s_h, p.s_m, "s")
    return bytes([_u8("new_ver", p.new_ver), _u8("day", p.day, 1, 7), sh, sm])


def _dec_slot_del(b: bytes) -> SlotDel:
    r = _Reader(b, "SLOT_DEL")
    nv = r.u8()
    d = r.u8()
    h = r.u8()
    m = r.u8()
    r.done()
    return SlotDel(nv, _u8("day", d, 1, 7), *_hm(h, m, "s"))


def _dec_day_clear(b: bytes) -> DayClear:
    r = _Reader(b, "DAY_CLEAR")
    nv = r.u8()
    d = r.u8()
    r.done()
    return DayClear(nv, _u8("day", d, 1, 7))


_register(P.Type.TIME, Time, _enc_time, _dec_time)
_register(
    P.Type.SLOT_SET,
    SlotSet,
    lambda p: bytes([_u8("new_ver", p.new_ver)]) + _slot_body(p),
    _dec_slot_set,
)
_register(P.Type.SLOT_DEL, SlotDel, _enc_slot_del, _dec_slot_del)
_register(
    P.Type.DAY_CLEAR,
    DayClear,
    lambda p: bytes([_u8("new_ver", p.new_ver), _u8("day", p.day, 1, 7)]),
    _dec_day_clear,
)


def type_of(obj: object) -> int:
    """페이로드 객체 → TYPE 코드."""
    try:
        return _ENCODERS[type(obj)][0]
    except KeyError:
        raise FrameError(f"페이로드 클래스 아님: {type(obj).__name__}") from None


def encode_payload(obj: object) -> bytes:
    _, enc = _ENCODERS.get(type(obj), (None, None))
    if enc is None:
        raise FrameError(f"페이로드 클래스 아님: {type(obj).__name__}")
    b = enc(obj)
    if len(b) > P.MAX_PAYLOAD:
        raise FrameError(f"{type(obj).__name__} 페이로드 {len(b)} B > {P.MAX_PAYLOAD}")
    return b


def decode_payload(type_: int, b: bytes) -> object:
    dec = _DECODERS.get(type_)
    if dec is None:
        raise FrameError(f"TYPE {type_:#x} 디코더 없음")
    return dec(b)
