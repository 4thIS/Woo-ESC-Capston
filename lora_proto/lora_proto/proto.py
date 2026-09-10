"""v2 §2·§3 상수의 Python 미러. 원본은 ../proto.h, ../radio_params.h — tools/check_mirror.py가 일치를 검사한다."""

from enum import IntEnum

# --- §3.1 헤더 ---
PROTO_VER = 2
FLAG_ACK_REQ = 0x01
FLAG_BROADCAST = 0x02
FLAG_WAKE_SENT = 0x04
HEADER_LEN = 9
MAX_FRAME = 255
MAX_PAYLOAD = 245
FILE_CHUNK_MAX = 200

# --- 주소 특수값 ---
BLD_UNPROVISIONED = 0x00
BLD_ALL = 0xFF
ROOM_ALL = 0xFFFF
UNIT_ALL = 0

# --- 문자열 한계 (§5.1) ---
SUBJ_MAX = 20
PROF_MAX = 12


class Type(IntEnum):
    TIME = 0x01
    SLOT_SET = 0x02
    SLOT_DEL = 0x03
    DAY_CLEAR = 0x04
    RESV_SET = 0x05
    RESV_DEL = 0x06
    EXAM_SET = 0x07
    EXAM_DEL = 0x08
    FILE_BEGIN = 0x09
    FILE_DATA = 0x0A
    FILE_END = 0x0B
    CMD = 0x0C
    SET_ROOM = 0x0D
    ACK = 0x10
    STATUS = 0x11
    HELLO = 0x12


class AckStatus(IntEnum):
    OK = 0x00
    BAD_CRC = 0x01
    BAD_PAYLOAD = 0x02
    STORE_FAIL = 0x03
    GAP = 0x04
    FILE_MISSING = 0x05
    UNSUPPORTED = 0x06
    BUSY = 0x07
    DUP = 0x08


class Cmd(IntEnum):
    TEST_RENDER = 0x01
    REBOOT = 0x02
    SET_PARAM = 0x03
    REQUEST_STATUS = 0x04
    FACTORY_RESET = 0x05
    FORCE_RENDER = 0x06


class SlotType(IntEnum):
    CLASS = 1
    EXAM = 2
    CANCELLED = 3
    EMPTY = 4
    SPECIAL = 5
    RENTAL = 6


class FileKind(IntEnum):
    SCHEDULE = 1
    RESV = 2
    EXAM = 3


class Layout(IntEnum):
    CLASS = 1
    BREAK = 2
    CANCELLED = 3
    EMPTY = 4
    EXAM = 5
    SPECIAL = 6
    RENTAL = 7
    SETUP = 8


class StatusFlag(IntEnum):
    CLOCK_STALE = 0x01
    UNPROVISIONED = 0x02
    LOW_BATT = 0x04


class TimeFlag(IntEnum):
    REQUEST_STATUS = 0x01


# --- §2 무선 파라미터 (radio_params.h 미러) ---
RADIO: dict[str, float | int] = {
    "RP_FREQ_MHZ": 922.5,
    "RP_BW_KHZ": 125.0,
    "RP_SF": 9,
    "RP_CR": 5,
    "RP_SYNC_WORD": 0x12,
    "RP_TX_POWER_DBM": 14,
    "RP_PREAMBLE_NORMAL": 8,
    "RP_PREAMBLE_WAKE_MS": 3000,
    "RP_RX_DUTY_MIN_SYM": 8,
    "RP_CAD_MAX_TRIES": 5,
    "RP_CAD_BACKOFF_MIN_MS": 50,
    "RP_CAD_BACKOFF_MAX_MS": 200,
    "RP_HW_CRC": 1,
    "RP_NET_ID": 0x4B,
}
NET_ID = RADIO["RP_NET_ID"]
