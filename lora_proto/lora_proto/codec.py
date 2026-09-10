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


# ---------- RESV · EXAM · CMD · SET_ROOM ----------


def _year(v: int) -> int:
    if not 2000 <= v <= 2255:
        raise FrameError(f"year={v} 는 2000..2255 밖 (wire 는 year-2000 u8)")
    return v - 2000


def _ymd(y: int, m: int, d: int) -> bytes:
    return bytes([_year(y), _u8("month", m, 1, 12), _u8("day", d, 1, 31)])


def _u16(name: str, v: int) -> bytes:
    if not 0 <= v <= 0xFFFF:
        raise FrameError(f"{name}={v} 는 u16 밖")
    return v.to_bytes(2, "big")


@dataclass(frozen=True)
class ResvSet:
    new_ver: int
    resv_id: int
    year: int
    month: int
    day: int
    s_h: int
    s_m: int
    e_h: int
    e_m: int
    type: int
    subject: str
    professor: str


@dataclass(frozen=True)
class ResvDel:
    new_ver: int
    resv_id: int


@dataclass(frozen=True)
class ExamSet:
    new_ver: int
    exam_id: int
    y1: int
    m1: int
    d1: int
    y2: int
    m2: int
    d2: int


@dataclass(frozen=True)
class ExamDel:
    new_ver: int
    exam_id: int


@dataclass(frozen=True)
class Cmd:
    cmd: int
    args: bytes = b""


@dataclass(frozen=True)
class SetRoom:
    new_ver: int
    mac: bytes
    bld: int
    room: int
    unit: int


def _resv_body(r: ResvSet) -> bytes:
    sh, sm = _hm(r.s_h, r.s_m, "s")
    eh, em = _hm(r.e_h, r.e_m, "e")
    return (
        _u16("resv_id", r.resv_id)
        + _ymd(r.year, r.month, r.day)
        + bytes([sh, sm, eh, em, _u8("type", r.type, 1, 6)])
        + _pack_str(r.subject, P.SUBJ_MAX, "subject")
        + _pack_str(r.professor, P.PROF_MAX, "professor")
    )


def _resv_read(r: _Reader, new_ver: int) -> ResvSet:
    rid = r.u16()
    y = r.u8()
    mo = r.u8()
    d = r.u8()
    sh = r.u8()
    sm = r.u8()
    eh = r.u8()
    em = r.u8()
    t = r.u8()
    subj = r.s(P.SUBJ_MAX, "subject")
    prof = r.s(P.PROF_MAX, "professor")
    return ResvSet(
        new_ver,
        rid,
        y + 2000,
        _u8("month", mo, 1, 12),
        _u8("day", d, 1, 31),
        *_hm(sh, sm, "s"),
        *_hm(eh, em, "e"),
        _u8("type", t, 1, 6),
        subj,
        prof,
    )


def _exam_body(e: ExamSet) -> bytes:
    return _u16("exam_id", e.exam_id) + _ymd(e.y1, e.m1, e.d1) + _ymd(e.y2, e.m2, e.d2)


def _exam_read(r: _Reader, new_ver: int) -> ExamSet:
    eid = r.u16()
    y1 = r.u8()
    m1 = r.u8()
    d1 = r.u8()
    y2 = r.u8()
    m2 = r.u8()
    d2 = r.u8()
    return ExamSet(
        new_ver,
        eid,
        y1 + 2000,
        _u8("month", m1, 1, 12),
        _u8("day", d1, 1, 31),
        y2 + 2000,
        _u8("month", m2, 1, 12),
        _u8("day", d2, 1, 31),
    )


def _dec_resv_set(b: bytes) -> ResvSet:
    r = _Reader(b, "RESV_SET")
    v = _resv_read(r, r.u8())
    r.done()
    return v


def _dec_resv_del(b: bytes) -> ResvDel:
    r = _Reader(b, "RESV_DEL")
    v = ResvDel(r.u8(), r.u16())
    r.done()
    return v


def _dec_exam_set(b: bytes) -> ExamSet:
    r = _Reader(b, "EXAM_SET")
    v = _exam_read(r, r.u8())
    r.done()
    return v


def _dec_exam_del(b: bytes) -> ExamDel:
    r = _Reader(b, "EXAM_DEL")
    v = ExamDel(r.u8(), r.u16())
    r.done()
    return v


def _enc_cmd(c: Cmd) -> bytes:
    if c.cmd not in P.Cmd.__members__.values():
        raise FrameError(f"cmd={c.cmd:#x} 는 §3.3 CMD 목록에 없음")
    return bytes([c.cmd]) + bytes(c.args)


def _dec_cmd(b: bytes) -> Cmd:
    r = _Reader(b, "CMD")
    c = r.u8()
    if c not in P.Cmd.__members__.values():
        raise FrameError(f"cmd={c:#x} 는 §3.3 CMD 목록에 없음")
    return Cmd(c, r.raw(len(b) - 1))


def _enc_set_room(s: SetRoom) -> bytes:
    if len(s.mac) != 6:
        raise FrameError(f"mac 은 6 B, {len(s.mac)} B 받음")
    return (
        bytes([_u8("new_ver", s.new_ver)])
        + bytes(s.mac)
        + bytes([_u8("bld", s.bld)])
        + _u16("room", s.room)
        + bytes([_u8("unit", s.unit, 0, 2)])
    )


def _dec_set_room(b: bytes) -> SetRoom:
    r = _Reader(b, "SET_ROOM")
    nv = r.u8()
    mac = r.raw(6)
    bld = r.u8()
    room = r.u16()
    unit = r.u8()
    r.done()
    return SetRoom(nv, mac, bld, room, _u8("unit", unit, 0, 2))


_register(
    P.Type.RESV_SET,
    ResvSet,
    lambda p: bytes([_u8("new_ver", p.new_ver)]) + _resv_body(p),
    _dec_resv_set,
)
_register(
    P.Type.RESV_DEL,
    ResvDel,
    lambda p: bytes([_u8("new_ver", p.new_ver)]) + _u16("resv_id", p.resv_id),
    _dec_resv_del,
)
_register(
    P.Type.EXAM_SET,
    ExamSet,
    lambda p: bytes([_u8("new_ver", p.new_ver)]) + _exam_body(p),
    _dec_exam_set,
)
_register(
    P.Type.EXAM_DEL,
    ExamDel,
    lambda p: bytes([_u8("new_ver", p.new_ver)]) + _u16("exam_id", p.exam_id),
    _dec_exam_del,
)
_register(P.Type.CMD, Cmd, _enc_cmd, _dec_cmd)
_register(P.Type.SET_ROOM, SetRoom, _enc_set_room, _dec_set_room)


# ---------- 업링크: ACK · STATUS · HELLO ----------


@dataclass(frozen=True)
class Ack:
    status: int
    detail: int
    batt_mv: int
    sched_ver: int
    resv_ver: int
    exam_ver: int
    ident_ver: int
    fw: int
    layout: int


@dataclass(frozen=True)
class Status:
    ack: Ack
    rssi_last: int  # i8
    snr_last_x4: int  # i8, SNR × 4
    flags: int
    uptime_h: int


@dataclass(frozen=True)
class Hello:
    mac: bytes
    fw: int
    batt_mv: int


def _i8(name: str, v: int) -> int:
    if not -128 <= v <= 127:
        raise FrameError(f"{name}={v} 는 i8 밖")
    return v & 0xFF


def _enc_ack(a: Ack) -> bytes:
    return (
        bytes(
            [
                _u8("status", a.status, 0, 8),
                _u8("detail", a.detail),
            ]
        )
        + _u16("batt_mv", a.batt_mv)
        + bytes(
            [
                _u8("sched_ver", a.sched_ver),
                _u8("resv_ver", a.resv_ver),
                _u8("exam_ver", a.exam_ver),
                _u8("ident_ver", a.ident_ver),
                _u8("fw", a.fw),
                _u8("layout", a.layout, 0, 8),
            ]
        )
    )


def _ack_read(r: _Reader) -> Ack:
    st = r.u8()
    det = r.u8()
    batt = r.u16()
    sv = r.u8()
    rv = r.u8()
    ev = r.u8()
    iv = r.u8()
    fw = r.u8()
    lay = r.u8()
    return Ack(_u8("status", st, 0, 8), det, batt, sv, rv, ev, iv, fw, _u8("layout", lay, 0, 8))


def _dec_ack(b: bytes) -> Ack:
    r = _Reader(b, "ACK")
    v = _ack_read(r)
    r.done()
    return v


def _enc_status(s: Status) -> bytes:
    return (
        _enc_ack(s.ack)
        + bytes(
            [
                _i8("rssi_last", s.rssi_last),
                _i8("snr_last_x4", s.snr_last_x4),
                _u8("flags", s.flags),
            ]
        )
        + _u16("uptime_h", s.uptime_h)
    )


def _dec_status(b: bytes) -> Status:
    r = _Reader(b, "STATUS")
    a = _ack_read(r)
    rssi = r.u8()
    snr = r.u8()
    fl = r.u8()
    up = r.u16()
    r.done()
    return Status(
        a,
        rssi - 256 if rssi > 127 else rssi,
        snr - 256 if snr > 127 else snr,
        fl,
        up,
    )


def _enc_hello(h: Hello) -> bytes:
    if len(h.mac) != 6:
        raise FrameError(f"mac 은 6 B, {len(h.mac)} B 받음")
    return bytes(h.mac) + bytes([_u8("fw", h.fw)]) + _u16("batt_mv", h.batt_mv)


def _dec_hello(b: bytes) -> Hello:
    r = _Reader(b, "HELLO")
    mac = r.raw(6)
    fw = r.u8()
    batt = r.u16()
    r.done()
    return Hello(mac, fw, batt)


_register(P.Type.ACK, Ack, _enc_ack, _dec_ack)
_register(P.Type.STATUS, Status, _enc_status, _dec_status)
_register(P.Type.HELLO, Hello, _enc_hello, _dec_hello)
