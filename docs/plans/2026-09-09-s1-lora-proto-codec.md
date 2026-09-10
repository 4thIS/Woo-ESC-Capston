# S1 — `lora_proto` + C++/Python codec + 테스트 벡터 + fake 모뎀 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-09
- 기준 spec: `docs/specs/2026-09-09-lora-v2-wor-design.md` §2·§3·§4.2·§4.3·§9·§10.1 (프로토콜 원본) + `docs/specs/2026-09-09-roadmap-design.md` §4(계약 ①②)·§5(S1)·§6.1(fake 모뎀)
- 담당: cw @ssenu. 브랜치 `cw`. 커밋 scope `feat(proto)` / `feat(firmware)` / `feat(modempi)`.

**Goal:** 공중 프레임 규격(v2 §3)을 Python과 C++ 두 벌로 구현하고, Python이 생성한 `test_vectors.json`을 C++ Unity 테스트가 바이트 단위로 재검증하며, 모뎀 시리얼 프로토콜(v2 §4.2·4.3)을 그대로 말하는 fake 모뎀을 만들어 이후 S2·S5·S6·S7·S8이 하드웨어 없이 개발할 수 있게 한다.

**Architecture:** `lora_proto/`는 Python 패키지(상수 `proto.py` + codec `codec.py` + 벡터 생성기)이자 C 헤더(`proto.h`·`radio_params.h`)의 집이다. 상수는 C 헤더가 원본이고 `tools/check_mirror.py`가 헤더를 파싱해 `proto.py`와 diff한다(CI). C++ codec은 `firmware/lib/lora_codec/`에 하드웨어 의존 없이 두고 `[env:native]`에서 Unity로 벡터를 검증한다. fake 모뎀은 `modempi/lora/fake_modem.py`에 두며 실물 `modem.py`(S6)와 같은 `ModemLike` 인터페이스를 구현한다.

**Tech Stack:** Python 3.12 + uv + pytest · PlatformIO `[env:native]` + Unity + ArduinoJson(벡터 파싱) · clang-format · ruff

## Global Constraints

- 프레임 총 길이 ≤ 255 B, 헤더 9 B, 페이로드 ≤ 245 B, FILE_DATA 청크 ≤ 200 B (v2 §3.1·§3.3)
- CRC8: poly 0x07, init 0x00, 헤더 offset 0부터 페이로드 끝까지 (v2 §3.1). FILE_END CRC16: CCITT-FALSE(poly 0x1021, init 0xFFFF), 파일 본문 전체 (v2 §3.3)
- 헤더 VER_FLAGS: 상위 4비트 = 2, 하위 4비트 플래그 bit0 ACK_REQ / bit1 BROADCAST / bit2 WAKE_SENT
- NET_ID 기본 0x4B (`RP_NET_ID`). ROOM u16 big-endian. 모든 멀티바이트 정수는 big-endian
- 문자열: UTF-8, 과목 ≤ 20 B, 교수 ≤ 12 B (v2 §5.1). 초과 시 codec은 **잘라내지 않고 에러** — 잘라내기는 상위 계층(메인Pi)의 책임
- 상수는 `lora_proto/` 한 곳에서만 정의. Python·C++가 같은 `test_vectors.json`으로 검증 (v2 원칙 4, §9)
- Python 3.12, uv, ruff. C++17, PlatformIO. 규율: 루트 `CLAUDE.md`, `firmware/CLAUDE.md`, `modempi/CLAUDE.md`
- 커밋은 Conventional Commits. `main` 직접 push 금지, 머지는 팀장만

---

## 파일 구조

```
lora_proto/
├── pyproject.toml              # 패키지 lora-proto (uv). modempi·server가 path 의존으로 설치
├── radio_params.h              # v2 §2 원본 그대로
├── proto.h                     # TYPE·status·cmd·layout·오프셋·한계 상수 (C 헤더, 원본)
├── lora_proto/
│   ├── __init__.py
│   ├── proto.py                # proto.h·radio_params.h 의 Python 미러 (IntEnum + 상수)
│   └── codec.py                # crc8/crc16, Header, 페이로드 dataclass, encode/decode, build_file
├── tools/
│   ├── check_mirror.py         # 헤더 파싱 ↔ proto.py diff (CI)
│   └── gen_vectors.py          # test_vectors.json 생성
├── test_vectors.json           # 생성물. 커밋한다 (C++ 테스트가 읽음)
└── tests/
    ├── test_crc.py
    ├── test_frame.py
    ├── test_payloads.py
    ├── test_file.py
    ├── test_mirror.py
    └── test_vectors.py         # 재생성 결과 == 커밋본 (드리프트 검사)

firmware/
├── platformio.ini              # [env:native] (terminal/modem env는 S7·S8에서 추가)
├── .clang-format
├── lib/lora_codec/
│   ├── lora_codec.h
│   └── lora_codec.cpp
└── test/test_codec/
    └── test_main.cpp           # Unity: test_vectors.json 라운드트립

modempi/
├── pyproject.toml              # 패키지 modempi (uv), lora-proto path 의존
├── modempi/
│   ├── __init__.py
│   └── lora/
│       ├── __init__.py
│       ├── modem_iface.py      # ModemLike Protocol + TxResult/RxEvent dataclass (S6 modem.py도 구현)
│       └── fake_modem.py       # v2 §4.2·4.3 JSON lines를 말하는 가짜 모뎀
└── tests/
    ├── test_fake_modem_basic.py
    ├── test_fake_modem_script.py
    └── test_fake_modem_node.py
```

책임 경계: `proto.py`는 값만, `codec.py`는 바이트 변환만, `fake_modem.py`는 시리얼 프로토콜 흉내만. 재시도·TXN 배정·큐는 S6이고 여기 없다.

---

### Task 1: `lora_proto` 패키지 뼈대 + `proto.py` 상수

**Files:**
- Create: `lora_proto/pyproject.toml`, `lora_proto/lora_proto/__init__.py`, `lora_proto/lora_proto/proto.py`, `lora_proto/tests/__init__.py`, `lora_proto/tests/test_proto_values.py`

**Interfaces:**
- Produces: `lora_proto.proto` — `PROTO_VER`, `FLAG_*`, `HEADER_LEN`, `MAX_FRAME`, `MAX_PAYLOAD`, `FILE_CHUNK_MAX`, `SUBJ_MAX`, `PROF_MAX`, `BLD_UNPROVISIONED`, `BLD_ALL`, `ROOM_ALL`, `UNIT_ALL`, `Type`, `AckStatus`, `Cmd`, `SlotType`, `FileKind`, `Layout`, `StatusFlag`, `TimeFlag`, `RADIO` (dict)

- [ ] **Step 1: 실패하는 테스트**

`lora_proto/tests/test_proto_values.py`:
```python
from lora_proto import proto as P


def test_header_constants_match_spec_3_1():
    assert P.PROTO_VER == 2
    assert P.HEADER_LEN == 9
    assert P.MAX_FRAME == 255
    assert P.MAX_PAYLOAD == 245
    assert P.FILE_CHUNK_MAX == 200
    assert (P.FLAG_ACK_REQ, P.FLAG_BROADCAST, P.FLAG_WAKE_SENT) == (0x01, 0x02, 0x04)


def test_type_codes_match_spec_3_2():
    assert P.Type.TIME == 0x01
    assert P.Type.SET_ROOM == 0x0D
    assert P.Type.ACK == 0x10
    assert P.Type.STATUS == 0x11
    assert P.Type.HELLO == 0x12
    assert len(P.Type) == 16


def test_ack_status_and_cmd_match_spec_3_3_3_4():
    assert P.AckStatus.GAP == 0x04
    assert P.AckStatus.DUP == 0x08
    assert P.Cmd.FORCE_RENDER == 0x06
    assert P.SlotType.RENTAL == 6
    assert P.Layout.SETUP == 8
    assert P.FileKind.EXAM == 3


def test_radio_params_match_spec_2():
    assert P.RADIO["RP_NET_ID"] == 0x4B
    assert P.RADIO["RP_SF"] == 9
    assert P.RADIO["RP_PREAMBLE_WAKE_MS"] == 3000
    assert P.RADIO["RP_FREQ_MHZ"] == 922.5
```

- [ ] **Step 2: 실패 확인**

Run: `cd lora_proto && uv run pytest tests/test_proto_values.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lora_proto'` (pyproject가 아직 없어 uv 자체가 실패할 수 있음 — 그러면 Step 3 후 다시)

- [ ] **Step 3: 구현**

`lora_proto/pyproject.toml`:
```toml
[project]
name = "lora-proto"
version = "2.0.0"
description = "Woo-ESC-Capston 공중 프로토콜 v2 — 상수·codec·테스트 벡터 (단일 진실원)"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["lora_proto"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`lora_proto/lora_proto/__init__.py`:
```python
"""공중 프로토콜 v2 — 상수(proto)와 바이트 변환(codec)."""

from . import codec, proto  # noqa: F401
```
(`codec`은 Task 3에서 생기므로 **이 Task에서는** `from . import proto  # noqa: F401` 한 줄만 두고, Task 3에서 `codec`을 추가한다.)

`lora_proto/lora_proto/proto.py`:
```python
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
```

`lora_proto/tests/__init__.py`: 빈 파일.

- [ ] **Step 4: 통과 확인**

Run: `cd lora_proto && uv sync && uv run pytest tests/test_proto_values.py -q`
Expected: `4 passed`

- [ ] **Step 5: 커밋**

```bash
git add lora_proto/pyproject.toml lora_proto/uv.lock lora_proto/lora_proto lora_proto/tests
git commit -m "feat(proto): lora_proto 패키지 뼈대와 v2 §2·§3 상수 미러"
```

---

### Task 2: C 헤더 원본(`proto.h`, `radio_params.h`) + 미러 검사기

**Files:**
- Create: `lora_proto/radio_params.h`, `lora_proto/proto.h`, `lora_proto/tools/__init__.py`, `lora_proto/tools/check_mirror.py`, `lora_proto/tests/test_mirror.py`

**Interfaces:**
- Produces: `proto.h`의 `LP_*` 매크로(C++ codec이 include), `check_mirror.diff() -> list[str]` (빈 리스트 = 일치), CLI `python -m tools.check_mirror` (불일치면 exit 1)

- [ ] **Step 1: 실패하는 테스트**

`lora_proto/tests/test_mirror.py`:
```python
from tools import check_mirror


def test_headers_and_python_mirror_agree():
    assert check_mirror.diff() == []


def test_parser_reads_hex_and_float_defines(tmp_path):
    h = tmp_path / "x.h"
    h.write_text("#define A 0x4B // c\n#define B 922.5f\n#define C 9\n", encoding="utf-8")
    assert check_mirror.parse_defines(h) == {"A": 0x4B, "B": 922.5, "C": 9}


def test_parser_reads_enum_values(tmp_path):
    h = tmp_path / "y.h"
    h.write_text("enum { LP_T_A = 0x01, LP_T_B = 0x10, };\n", encoding="utf-8")
    assert check_mirror.parse_defines(h) == {"LP_T_A": 1, "LP_T_B": 16}
```

- [ ] **Step 2: 실패 확인**

Run: `cd lora_proto && uv run pytest tests/test_mirror.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools'`

- [ ] **Step 3: 구현**

`lora_proto/radio_params.h` — v2 §2 코드 블록을 **그대로** 복사 (주석 포함), 앞뒤에 include guard:
```c
#ifndef LORA_PROTO_RADIO_PARAMS_H
#define LORA_PROTO_RADIO_PARAMS_H
// v2 스펙 §2 원본. 바꾸면 lora_proto/proto.py RADIO 와 test_vectors.json 을 같은 커밋에서 갱신한다.
#define RP_FREQ_MHZ          922.5f
#define RP_BW_KHZ            125.0f
#define RP_SF                9
#define RP_CR                5
#define RP_SYNC_WORD         0x12
#define RP_TX_POWER_DBM      14
#define RP_PREAMBLE_NORMAL   8
#define RP_PREAMBLE_WAKE_MS  3000
#define RP_RX_DUTY_MIN_SYM   8
#define RP_CAD_MAX_TRIES     5
#define RP_CAD_BACKOFF_MIN_MS 50
#define RP_CAD_BACKOFF_MAX_MS 200
#define RP_HW_CRC            1
#define RP_NET_ID            0x4B
#endif
```

`lora_proto/proto.h`:
```c
#ifndef LORA_PROTO_PROTO_H
#define LORA_PROTO_PROTO_H
// v2 스펙 §3 상수 원본. Python 미러는 lora_proto/proto.py — tools/check_mirror.py 가 일치를 검사한다.
// 이름 규칙: LP_<GROUP>_<NAME>. check_mirror 는 <GROUP> 을 proto.py 의 enum 클래스에 매핑한다.

#define LP_PROTO_VER      2
#define LP_FLAG_ACK_REQ   0x01
#define LP_FLAG_BROADCAST 0x02
#define LP_FLAG_WAKE_SENT 0x04
#define LP_HEADER_LEN     9
#define LP_MAX_FRAME      255
#define LP_MAX_PAYLOAD    245
#define LP_FILE_CHUNK_MAX 200
#define LP_BLD_UNPROVISIONED 0x00
#define LP_BLD_ALL        0xFF
#define LP_ROOM_ALL       0xFFFF
#define LP_UNIT_ALL       0
#define LP_SUBJ_MAX       20
#define LP_PROF_MAX       12

enum {
  LP_TYPE_TIME = 0x01, LP_TYPE_SLOT_SET = 0x02, LP_TYPE_SLOT_DEL = 0x03, LP_TYPE_DAY_CLEAR = 0x04,
  LP_TYPE_RESV_SET = 0x05, LP_TYPE_RESV_DEL = 0x06, LP_TYPE_EXAM_SET = 0x07, LP_TYPE_EXAM_DEL = 0x08,
  LP_TYPE_FILE_BEGIN = 0x09, LP_TYPE_FILE_DATA = 0x0A, LP_TYPE_FILE_END = 0x0B, LP_TYPE_CMD = 0x0C,
  LP_TYPE_SET_ROOM = 0x0D, LP_TYPE_ACK = 0x10, LP_TYPE_STATUS = 0x11, LP_TYPE_HELLO = 0x12,
};
enum {
  LP_ACK_OK = 0x00, LP_ACK_BAD_CRC = 0x01, LP_ACK_BAD_PAYLOAD = 0x02, LP_ACK_STORE_FAIL = 0x03,
  LP_ACK_GAP = 0x04, LP_ACK_FILE_MISSING = 0x05, LP_ACK_UNSUPPORTED = 0x06, LP_ACK_BUSY = 0x07, LP_ACK_DUP = 0x08,
};
enum {
  LP_CMD_TEST_RENDER = 0x01, LP_CMD_REBOOT = 0x02, LP_CMD_SET_PARAM = 0x03,
  LP_CMD_REQUEST_STATUS = 0x04, LP_CMD_FACTORY_RESET = 0x05, LP_CMD_FORCE_RENDER = 0x06,
};
enum { LP_SLOTTYPE_CLASS = 1, LP_SLOTTYPE_EXAM = 2, LP_SLOTTYPE_CANCELLED = 3, LP_SLOTTYPE_EMPTY = 4, LP_SLOTTYPE_SPECIAL = 5, LP_SLOTTYPE_RENTAL = 6 };
enum { LP_FILEKIND_SCHEDULE = 1, LP_FILEKIND_RESV = 2, LP_FILEKIND_EXAM = 3 };
enum { LP_LAYOUT_CLASS = 1, LP_LAYOUT_BREAK = 2, LP_LAYOUT_CANCELLED = 3, LP_LAYOUT_EMPTY = 4, LP_LAYOUT_EXAM = 5, LP_LAYOUT_SPECIAL = 6, LP_LAYOUT_RENTAL = 7, LP_LAYOUT_SETUP = 8 };
enum { LP_STATUSFLAG_CLOCK_STALE = 0x01, LP_STATUSFLAG_UNPROVISIONED = 0x02, LP_STATUSFLAG_LOW_BATT = 0x04 };
enum { LP_TIMEFLAG_REQUEST_STATUS = 0x01 };
#endif
```

`lora_proto/tools/__init__.py`: 빈 파일.

`lora_proto/tools/check_mirror.py`:
```python
"""proto.h·radio_params.h 를 파싱해 lora_proto/proto.py 와 값이 같은지 검사한다. CI 게이트."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from lora_proto import proto as P

ROOT = Path(__file__).resolve().parents[1]
_DEFINE = re.compile(r"^\s*#define\s+(\w+)\s+([0-9A-Fa-fx.]+)f?\b")
_ENUM_ITEM = re.compile(r"(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)")

# LP_<GROUP>_<NAME> 의 GROUP → proto.py 의 enum 클래스
_GROUPS = {
    "TYPE": P.Type, "ACK": P.AckStatus, "CMD": P.Cmd, "SLOTTYPE": P.SlotType,
    "FILEKIND": P.FileKind, "LAYOUT": P.Layout, "STATUSFLAG": P.StatusFlag, "TIMEFLAG": P.TimeFlag,
}
# 단순 #define → proto.py 모듈 상수
_SCALARS = {
    "LP_PROTO_VER": "PROTO_VER", "LP_FLAG_ACK_REQ": "FLAG_ACK_REQ", "LP_FLAG_BROADCAST": "FLAG_BROADCAST",
    "LP_FLAG_WAKE_SENT": "FLAG_WAKE_SENT", "LP_HEADER_LEN": "HEADER_LEN", "LP_MAX_FRAME": "MAX_FRAME",
    "LP_MAX_PAYLOAD": "MAX_PAYLOAD", "LP_FILE_CHUNK_MAX": "FILE_CHUNK_MAX",
    "LP_BLD_UNPROVISIONED": "BLD_UNPROVISIONED", "LP_BLD_ALL": "BLD_ALL", "LP_ROOM_ALL": "ROOM_ALL",
    "LP_UNIT_ALL": "UNIT_ALL", "LP_SUBJ_MAX": "SUBJ_MAX", "LP_PROF_MAX": "PROF_MAX",
}


def _num(s: str) -> int | float:
    return int(s, 16) if s.lower().startswith("0x") else (float(s) if "." in s else int(s))


def parse_defines(path: Path) -> dict[str, int | float]:
    out: dict[str, int | float] = {}
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = _DEFINE.match(line)
        if m and m.group(1) not in ("LORA_PROTO_PROTO_H", "LORA_PROTO_RADIO_PARAMS_H"):
            out[m.group(1)] = _num(m.group(2))
    for body in re.findall(r"enum\s*\{([^}]*)\}", text, re.S):
        for name, val in _ENUM_ITEM.findall(body):
            out[name] = _num(val)
    return out


def diff() -> list[str]:
    problems: list[str] = []
    h = parse_defines(ROOT / "proto.h")
    r = parse_defines(ROOT / "radio_params.h")

    for cname, pname in _SCALARS.items():
        if cname not in h:
            problems.append(f"proto.h 에 {cname} 없음")
        elif h[cname] != getattr(P, pname):
            problems.append(f"{cname}={h[cname]} != proto.{pname}={getattr(P, pname)}")

    for cname, val in h.items():
        if cname in _SCALARS:
            continue
        group, _, name = cname.removeprefix("LP_").partition("_")
        enum = _GROUPS.get(group)
        if enum is None:
            problems.append(f"proto.h {cname}: 알 수 없는 그룹 {group}")
        elif name not in enum.__members__:
            problems.append(f"proto.py {enum.__name__} 에 {name} 없음")
        elif enum[name] != val:
            problems.append(f"{cname}={val} != proto.{enum.__name__}.{name}={int(enum[name])}")
    for enum in _GROUPS.values():
        for name in enum.__members__:
            group = next(g for g, e in _GROUPS.items() if e is enum)
            if f"LP_{group}_{name}" not in h:
                problems.append(f"proto.h 에 LP_{group}_{name} 없음 (proto.py 에만 있음)")

    for k, v in r.items():
        if k not in P.RADIO:
            problems.append(f"proto.RADIO 에 {k} 없음")
        elif P.RADIO[k] != v:
            problems.append(f"{k}={v} != proto.RADIO[{k}]={P.RADIO[k]}")
    for k in P.RADIO:
        if k not in r:
            problems.append(f"radio_params.h 에 {k} 없음 (proto.py 에만 있음)")
    return problems


if __name__ == "__main__":
    d = diff()
    for line in d:
        print("MISMATCH:", line)
    print("OK: 헤더와 proto.py 일치" if not d else f"{len(d)}건 불일치")
    sys.exit(1 if d else 0)
```

- [ ] **Step 4: 통과 확인**

Run: `cd lora_proto && uv run pytest tests/test_mirror.py -q && uv run python -m tools.check_mirror`
Expected: `3 passed` 그리고 `OK: 헤더와 proto.py 일치`

- [ ] **Step 5: 커밋**

```bash
git add lora_proto/proto.h lora_proto/radio_params.h lora_proto/tools lora_proto/tests/test_mirror.py
git commit -m "feat(proto): C 헤더 원본과 Python 미러 일치 검사기"
```

---

### Task 3: `codec.py` — CRC8 · CRC16 · 헤더 · 프레임 조립/분해

**Files:**
- Create: `lora_proto/lora_proto/codec.py`, `lora_proto/tests/test_crc.py`, `lora_proto/tests/test_frame.py`
- Modify: `lora_proto/lora_proto/__init__.py` (`codec` import 추가)

**Interfaces:**
- Produces: `crc8(data: bytes) -> int`, `crc16_ccitt(data: bytes) -> int`, `class FrameError(ValueError)`, `@dataclass Header(type, bld, room, unit, txn, flags=0, net_id=NET_ID, ver=PROTO_VER)`, `encode_frame(h: Header, payload: bytes) -> bytes`, `decode_frame(buf: bytes, *, net_id: int = NET_ID) -> tuple[Header, bytes]`, `Header.matches_ack(other: Header) -> bool`

- [ ] **Step 1: 실패하는 테스트**

`lora_proto/tests/test_crc.py`:
```python
from lora_proto.codec import crc8, crc16_ccitt


def test_crc8_poly07_known_vectors():
    # CRC-8 (poly 0x07, init 0x00, no reflect, xorout 0) 표준 check 값
    assert crc8(b"123456789") == 0xF4
    assert crc8(b"") == 0x00
    assert crc8(b"\x00") == 0x00
    assert crc8(b"\x01") == 0x07


def test_crc16_ccitt_false_known_vectors():
    assert crc16_ccitt(b"123456789") == 0x29B1
    assert crc16_ccitt(b"") == 0xFFFF
```

`lora_proto/tests/test_frame.py`:
```python
import pytest

from lora_proto import proto as P
from lora_proto.codec import FrameError, Header, crc8, decode_frame, encode_frame


def test_header_layout_matches_spec_3_1():
    h = Header(type=P.Type.SLOT_SET, bld=ord("E"), room=301, unit=1, txn=7, flags=P.FLAG_ACK_REQ)
    frame = encode_frame(h, b"\x03\x01")
    assert frame[0] == 0x21                      # ver 2 <<4 | ACK_REQ
    assert frame[1] == P.NET_ID
    assert frame[2] == P.Type.SLOT_SET
    assert frame[3] == ord("E")
    assert frame[4:6] == (301).to_bytes(2, "big")
    assert frame[6] == 1
    assert frame[7] == 7
    assert frame[8] == 2                         # LEN
    assert frame[9:11] == b"\x03\x01"
    assert frame[11] == crc8(frame[:11])
    assert len(frame) == P.HEADER_LEN + 2 + 1


def test_roundtrip():
    h = Header(type=P.Type.TIME, bld=P.BLD_ALL, room=P.ROOM_ALL, unit=0, txn=0, flags=P.FLAG_BROADCAST)
    payload = bytes(range(245))
    h2, p2 = decode_frame(encode_frame(h, payload))
    assert h2 == h and p2 == payload


def test_payload_too_long_rejected():
    h = Header(type=P.Type.TIME, bld=P.BLD_ALL, room=P.ROOM_ALL, unit=0, txn=0)
    with pytest.raises(FrameError):
        encode_frame(h, bytes(246))


@pytest.mark.parametrize("mutate", [
    lambda f: f[:-1] + bytes([f[-1] ^ 0xFF]),        # CRC 깨짐
    lambda f: f[:1] + bytes([0x00]) + f[2:],         # NET_ID 불일치
    lambda f: bytes([0x30]) + f[1:],                 # 프로토콜 버전 3
    lambda f: f[:8] + bytes([9]) + f[9:],            # LEN 이 실제보다 큼
    lambda f: f[:5],                                 # 헤더보다 짧음
])
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
```

- [ ] **Step 2: 실패 확인**

Run: `cd lora_proto && uv run pytest tests/test_crc.py tests/test_frame.py -q`
Expected: FAIL — `ImportError: cannot import name 'crc8' from 'lora_proto.codec'` (모듈 없음)

- [ ] **Step 3: 구현**

`lora_proto/lora_proto/codec.py` (이 Task에서는 여기까지만. 페이로드 부분은 Task 4·5·6에서 같은 파일에 이어 붙인다):
```python
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
    bld: int          # ASCII 코드 ('E'=0x45) 또는 BLD_UNPROVISIONED/BLD_ALL
    room: int         # 1..9999 또는 ROOM_ALL
    unit: int         # 0 전체 / 1 앞문 / 2 뒷문
    txn: int          # 1..255, 업링크·브로드캐스트는 0
    flags: int = 0
    net_id: int = P.NET_ID
    ver: int = P.PROTO_VER

    def matches_ack(self, other: Header) -> bool:
        """v2 §4.4: ACK 는 [NET_ID, TYPE==ACK, BLD/ROOM/UNIT/TXN] 이 송신 헤더와 같아야 한다."""
        return (
            other.type == P.Type.ACK
            and other.net_id == self.net_id
            and (other.bld, other.room, other.unit, other.txn) == (self.bld, self.room, self.unit, self.txn)
        )


def _check_u8(name: str, v: int) -> None:
    if not 0 <= v <= 0xFF:
        raise FrameError(f"{name}={v} 는 u8 범위 밖")


def encode_frame(h: Header, payload: bytes) -> bytes:
    if len(payload) > P.MAX_PAYLOAD:
        raise FrameError(f"payload {len(payload)} B > {P.MAX_PAYLOAD}")
    for name, v in (("bld", h.bld), ("unit", h.unit), ("txn", h.txn), ("type", h.type), ("net_id", h.net_id)):
        _check_u8(name, v)
    if not 0 <= h.room <= 0xFFFF:
        raise FrameError(f"room={h.room} 는 u16 범위 밖")
    if h.flags & ~0x0F:
        raise FrameError(f"flags={h.flags:#x} 는 4비트 초과")
    head = bytes([
        (h.ver << 4) | h.flags, h.net_id, h.type, h.bld,
        (h.room >> 8) & 0xFF, h.room & 0xFF, h.unit, h.txn, len(payload),
    ])
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
        type=buf[2], bld=buf[3], room=(buf[4] << 8) | buf[5], unit=buf[6], txn=buf[7],
        flags=buf[0] & 0x0F, net_id=buf[1], ver=ver,
    )
    return h, bytes(buf[P.HEADER_LEN:P.HEADER_LEN + ln])
```

`lora_proto/lora_proto/__init__.py`를 다음으로 교체:
```python
"""공중 프로토콜 v2 — 상수(proto)와 바이트 변환(codec)."""

from . import codec, proto  # noqa: F401
```

- [ ] **Step 4: 통과 확인**

Run: `cd lora_proto && uv run pytest -q`
Expected: 모두 PASS (test_crc 2, test_frame 9 포함)

- [ ] **Step 5: 커밋**

```bash
git add lora_proto/lora_proto/codec.py lora_proto/lora_proto/__init__.py lora_proto/tests/test_crc.py lora_proto/tests/test_frame.py
git commit -m "feat(proto): CRC8/CRC16, 헤더, 프레임 조립·분해"
```

---

### Task 4: 페이로드 codec ① — TIME · SLOT_SET · SLOT_DEL · DAY_CLEAR · 문자열 규칙

**Files:**
- Modify: `lora_proto/lora_proto/codec.py` (끝에 추가)
- Create: `lora_proto/tests/test_payloads.py`

**Interfaces:**
- Produces: dataclass `Time(epoch, flags=0)`, `SlotSet(new_ver, day, s_h, s_m, e_h, e_m, type, subject, professor)`, `SlotDel(new_ver, day, s_h, s_m)`, `DayClear(new_ver, day)`; `encode_payload(obj) -> bytes`; `decode_payload(type_: int, b: bytes) -> object`; 내부 `_pack_str(s, max_len, name) -> bytes`, `_Reader`
- 규칙: `subject`·`professor`는 UTF-8 인코딩 후 각각 ≤ 20 B·≤ 12 B. 초과·잘못된 시각(시 > 23, 분 > 59)·day 1~7 밖이면 `FrameError`

- [ ] **Step 1: 실패하는 테스트**

`lora_proto/tests/test_payloads.py` (이 Task 분량):
```python
import pytest

from lora_proto import proto as P
from lora_proto.codec import (
    DayClear, FrameError, SlotDel, SlotSet, Time, decode_payload, encode_payload,
)


def test_time_layout():
    b = encode_payload(Time(epoch=1_757_400_000, flags=P.TimeFlag.REQUEST_STATUS))
    assert b == (1_757_400_000).to_bytes(4, "big") + b"\x01"
    assert decode_payload(P.Type.TIME, b) == Time(epoch=1_757_400_000, flags=1)


def test_slot_set_layout_and_roundtrip():
    s = SlotSet(new_ver=3, day=3, s_h=9, s_m=0, e_h=10, e_m=50, type=P.SlotType.CLASS,
                subject="임베디드시스템", professor="정필성")
    b = encode_payload(s)
    subj = "임베디드시스템".encode(); prof = "정필성".encode()
    assert b == bytes([3, 3, 9, 0, 10, 50, 1, len(subj)]) + subj + bytes([len(prof)]) + prof
    assert decode_payload(P.Type.SLOT_SET, b) == s


def test_slot_set_string_limits():
    ok = SlotSet(1, 1, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4)       # 20 B, 12 B
    encode_payload(ok)
    with pytest.raises(FrameError):
        encode_payload(SlotSet(1, 1, 9, 0, 10, 0, 1, "가" * 7, "x"))   # 21 B
    with pytest.raises(FrameError):
        encode_payload(SlotSet(1, 1, 9, 0, 10, 0, 1, "x", "가" * 5))   # 15 B


@pytest.mark.parametrize("bad", [
    dict(day=0), dict(day=8), dict(s_h=24), dict(s_m=60), dict(e_h=24), dict(new_ver=256), dict(type=0), dict(type=7),
])
def test_slot_set_field_ranges(bad):
    base = dict(new_ver=1, day=1, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="s", professor="p")
    with pytest.raises(FrameError):
        encode_payload(SlotSet(**{**base, **bad}))


def test_slot_del_and_day_clear():
    assert encode_payload(SlotDel(5, 2, 13, 30)) == bytes([5, 2, 13, 30])
    assert decode_payload(P.Type.SLOT_DEL, bytes([5, 2, 13, 30])) == SlotDel(5, 2, 13, 30)
    assert encode_payload(DayClear(6, 7)) == bytes([6, 7])
    assert decode_payload(P.Type.DAY_CLEAR, bytes([6, 7])) == DayClear(6, 7)


def test_decode_truncated_payload_raises():
    with pytest.raises(FrameError):
        decode_payload(P.Type.SLOT_SET, bytes([3, 3, 9, 0, 10, 50, 1, 5, 0x41]))   # subjLen 5 인데 1 B
    with pytest.raises(FrameError):
        decode_payload(P.Type.TIME, b"\x00\x00\x00")


def test_decode_trailing_bytes_raises():
    with pytest.raises(FrameError):
        decode_payload(P.Type.DAY_CLEAR, bytes([6, 7, 9]))
```

- [ ] **Step 2: 실패 확인**

Run: `cd lora_proto && uv run pytest tests/test_payloads.py -q`
Expected: FAIL — `ImportError: cannot import name 'DayClear'`

- [ ] **Step 3: 구현** — `codec.py` 끝에 추가

```python
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
        v = self.b[self.i]; self.i += 1
        return v

    def u16(self) -> int:
        return (self.u8() << 8) | self.u8()

    def u32(self) -> int:
        return (self.u16() << 16) | self.u16()

    def raw(self, n: int) -> bytes:
        if self.i + n > len(self.b):
            raise FrameError(f"{self.what}: {n} B 필요, {len(self.b) - self.i} B 남음")
        v = self.b[self.i:self.i + n]; self.i += n
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
    sh, sm = _hm(s.s_h, s.s_m, "s"); eh, em = _hm(s.e_h, s.e_m, "e")
    return (bytes([_u8("day", s.day, 1, 7), sh, sm, eh, em, _u8("type", s.type, 1, 6)])
            + _pack_str(s.subject, P.SUBJ_MAX, "subject") + _pack_str(s.professor, P.PROF_MAX, "professor"))


def _slot_read(r: _Reader, new_ver: int) -> SlotSet:
    day = r.u8(); sh = r.u8(); sm = r.u8(); eh = r.u8(); em = r.u8(); t = r.u8()
    subj = r.s(P.SUBJ_MAX, "subject"); prof = r.s(P.PROF_MAX, "professor")
    return SlotSet(new_ver, _u8("day", day, 1, 7), *_hm(sh, sm, "s"), *_hm(eh, em, "e"), _u8("type", t, 1, 6), subj, prof)


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
    r = _Reader(b, "TIME"); v = Time(r.u32(), r.u8()); r.done(); return v


def _dec_slot_set(b: bytes) -> SlotSet:
    r = _Reader(b, "SLOT_SET"); v = _slot_read(r, r.u8()); r.done(); return v


def _enc_slot_del(p: SlotDel) -> bytes:
    sh, sm = _hm(p.s_h, p.s_m, "s")
    return bytes([_u8("new_ver", p.new_ver), _u8("day", p.day, 1, 7), sh, sm])


def _dec_slot_del(b: bytes) -> SlotDel:
    r = _Reader(b, "SLOT_DEL"); nv = r.u8(); d = r.u8(); h = r.u8(); m = r.u8(); r.done()
    return SlotDel(nv, _u8("day", d, 1, 7), *_hm(h, m, "s"))


def _dec_day_clear(b: bytes) -> DayClear:
    r = _Reader(b, "DAY_CLEAR"); nv = r.u8(); d = r.u8(); r.done()
    return DayClear(nv, _u8("day", d, 1, 7))


_register(P.Type.TIME, Time, _enc_time, _dec_time)
_register(P.Type.SLOT_SET, SlotSet, lambda p: bytes([_u8("new_ver", p.new_ver)]) + _slot_body(p), _dec_slot_set)
_register(P.Type.SLOT_DEL, SlotDel, _enc_slot_del, _dec_slot_del)
_register(P.Type.DAY_CLEAR, DayClear, lambda p: bytes([_u8("new_ver", p.new_ver), _u8("day", p.day, 1, 7)]), _dec_day_clear)


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
```

- [ ] **Step 4: 통과 확인**

Run: `cd lora_proto && uv run pytest -q`
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add lora_proto/lora_proto/codec.py lora_proto/tests/test_payloads.py
git commit -m "feat(proto): TIME·SLOT_SET·SLOT_DEL·DAY_CLEAR 페이로드 codec"
```

---

### Task 5: 페이로드 codec ② — RESV · EXAM · CMD · SET_ROOM · ACK · STATUS · HELLO

**Files:**
- Modify: `lora_proto/lora_proto/codec.py` (끝에 추가), `lora_proto/tests/test_payloads.py` (끝에 추가)

**Interfaces:**
- Produces: `ResvSet(new_ver, resv_id, year, month, day, s_h, s_m, e_h, e_m, type, subject, professor)`, `ResvDel(new_ver, resv_id)`, `ExamSet(new_ver, exam_id, y1, m1, d1, y2, m2, d2)`, `ExamDel(new_ver, exam_id)`, `Cmd(cmd, args=b"")`, `SetRoom(new_ver, mac: bytes, bld, room, unit)`, `Ack(status, detail, batt_mv, sched_ver, resv_ver, exam_ver, ident_ver, fw, layout)`, `Status(ack: Ack, rssi_last, snr_last_x4, flags, uptime_h)`, `Hello(mac: bytes, fw, batt_mv)`
- 연도는 **실제 연도**(예 2026)로 다루고 wire 에선 `year-2000` u8. `mac`은 6 B `bytes`. `snr_last_x4`는 i8(부호 있음), `rssi_last`도 i8

- [ ] **Step 1: 실패하는 테스트** — `tests/test_payloads.py` 끝에 추가

```python
from lora_proto.codec import (  # noqa: E402
    Ack, Cmd, ExamDel, ExamSet, Hello, ResvDel, ResvSet, SetRoom, Status,
)


def test_resv_set_layout_and_roundtrip():
    r = ResvSet(new_ver=2, resv_id=0x0102, year=2026, month=11, day=19, s_h=13, s_m=0, e_h=15, e_m=0,
                type=P.SlotType.RENTAL, subject="경진대회", professor="산학처")
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


@pytest.mark.parametrize("bad", [dict(year=1999), dict(year=2256), dict(month=13), dict(day=0), dict(day=32)])
def test_resv_date_ranges(bad):
    base = dict(new_ver=1, resv_id=1, year=2026, month=1, day=1, s_h=9, s_m=0, e_h=10, e_m=0,
                type=1, subject="s", professor="p")
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
    a = Ack(status=P.AckStatus.GAP, detail=0, batt_mv=3987, sched_ver=12, resv_ver=3, exam_ver=1,
            ident_ver=1, fw=20, layout=P.Layout.CLASS)
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
```

- [ ] **Step 2: 실패 확인**

Run: `cd lora_proto && uv run pytest tests/test_payloads.py -q`
Expected: FAIL — `ImportError: cannot import name 'Ack'`

- [ ] **Step 3: 구현** — `codec.py` 끝에 추가

```python
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
    sh, sm = _hm(r.s_h, r.s_m, "s"); eh, em = _hm(r.e_h, r.e_m, "e")
    return (_u16("resv_id", r.resv_id) + _ymd(r.year, r.month, r.day)
            + bytes([sh, sm, eh, em, _u8("type", r.type, 1, 6)])
            + _pack_str(r.subject, P.SUBJ_MAX, "subject") + _pack_str(r.professor, P.PROF_MAX, "professor"))


def _resv_read(r: _Reader, new_ver: int) -> ResvSet:
    rid = r.u16(); y = r.u8(); mo = r.u8(); d = r.u8(); sh = r.u8(); sm = r.u8(); eh = r.u8(); em = r.u8(); t = r.u8()
    subj = r.s(P.SUBJ_MAX, "subject"); prof = r.s(P.PROF_MAX, "professor")
    return ResvSet(new_ver, rid, y + 2000, _u8("month", mo, 1, 12), _u8("day", d, 1, 31),
                   *_hm(sh, sm, "s"), *_hm(eh, em, "e"), _u8("type", t, 1, 6), subj, prof)


def _exam_body(e: ExamSet) -> bytes:
    return _u16("exam_id", e.exam_id) + _ymd(e.y1, e.m1, e.d1) + _ymd(e.y2, e.m2, e.d2)


def _exam_read(r: _Reader, new_ver: int) -> ExamSet:
    eid = r.u16(); y1 = r.u8(); m1 = r.u8(); d1 = r.u8(); y2 = r.u8(); m2 = r.u8(); d2 = r.u8()
    return ExamSet(new_ver, eid, y1 + 2000, _u8("month", m1, 1, 12), _u8("day", d1, 1, 31),
                   y2 + 2000, _u8("month", m2, 1, 12), _u8("day", d2, 1, 31))


def _dec_resv_set(b: bytes) -> ResvSet:
    r = _Reader(b, "RESV_SET"); v = _resv_read(r, r.u8()); r.done(); return v


def _dec_resv_del(b: bytes) -> ResvDel:
    r = _Reader(b, "RESV_DEL"); v = ResvDel(r.u8(), r.u16()); r.done(); return v


def _dec_exam_set(b: bytes) -> ExamSet:
    r = _Reader(b, "EXAM_SET"); v = _exam_read(r, r.u8()); r.done(); return v


def _dec_exam_del(b: bytes) -> ExamDel:
    r = _Reader(b, "EXAM_DEL"); v = ExamDel(r.u8(), r.u16()); r.done(); return v


def _enc_cmd(c: Cmd) -> bytes:
    if c.cmd not in P.Cmd.__members__.values():
        raise FrameError(f"cmd={c.cmd:#x} 는 §3.3 CMD 목록에 없음")
    return bytes([c.cmd]) + bytes(c.args)


def _dec_cmd(b: bytes) -> Cmd:
    r = _Reader(b, "CMD"); c = r.u8()
    if c not in P.Cmd.__members__.values():
        raise FrameError(f"cmd={c:#x} 는 §3.3 CMD 목록에 없음")
    return Cmd(c, r.raw(len(b) - 1))


def _enc_set_room(s: SetRoom) -> bytes:
    if len(s.mac) != 6:
        raise FrameError(f"mac 은 6 B, {len(s.mac)} B 받음")
    return (bytes([_u8("new_ver", s.new_ver)]) + bytes(s.mac)
            + bytes([_u8("bld", s.bld)]) + _u16("room", s.room) + bytes([_u8("unit", s.unit, 0, 2)]))


def _dec_set_room(b: bytes) -> SetRoom:
    r = _Reader(b, "SET_ROOM"); nv = r.u8(); mac = r.raw(6); bld = r.u8(); room = r.u16(); unit = r.u8(); r.done()
    return SetRoom(nv, mac, bld, room, _u8("unit", unit, 0, 2))


_register(P.Type.RESV_SET, ResvSet, lambda p: bytes([_u8("new_ver", p.new_ver)]) + _resv_body(p), _dec_resv_set)
_register(P.Type.RESV_DEL, ResvDel, lambda p: bytes([_u8("new_ver", p.new_ver)]) + _u16("resv_id", p.resv_id), _dec_resv_del)
_register(P.Type.EXAM_SET, ExamSet, lambda p: bytes([_u8("new_ver", p.new_ver)]) + _exam_body(p), _dec_exam_set)
_register(P.Type.EXAM_DEL, ExamDel, lambda p: bytes([_u8("new_ver", p.new_ver)]) + _u16("exam_id", p.exam_id), _dec_exam_del)
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
    rssi_last: int      # i8
    snr_last_x4: int    # i8, SNR × 4
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
    return (bytes([_u8("status", a.status, 0, 8), _u8("detail", a.detail)]) + _u16("batt_mv", a.batt_mv)
            + bytes([_u8("sched_ver", a.sched_ver), _u8("resv_ver", a.resv_ver), _u8("exam_ver", a.exam_ver),
                     _u8("ident_ver", a.ident_ver), _u8("fw", a.fw), _u8("layout", a.layout, 0, 8)]))


def _ack_read(r: _Reader) -> Ack:
    st = r.u8(); det = r.u8(); batt = r.u16(); sv = r.u8(); rv = r.u8(); ev = r.u8(); iv = r.u8(); fw = r.u8(); lay = r.u8()
    return Ack(_u8("status", st, 0, 8), det, batt, sv, rv, ev, iv, fw, _u8("layout", lay, 0, 8))


def _dec_ack(b: bytes) -> Ack:
    r = _Reader(b, "ACK"); v = _ack_read(r); r.done(); return v


def _enc_status(s: Status) -> bytes:
    return (_enc_ack(s.ack) + bytes([_i8("rssi_last", s.rssi_last), _i8("snr_last_x4", s.snr_last_x4),
                                     _u8("flags", s.flags)]) + _u16("uptime_h", s.uptime_h))


def _dec_status(b: bytes) -> Status:
    r = _Reader(b, "STATUS"); a = _ack_read(r)
    rssi = r.u8(); snr = r.u8(); fl = r.u8(); up = r.u16(); r.done()
    return Status(a, rssi - 256 if rssi > 127 else rssi, snr - 256 if snr > 127 else snr, fl, up)


def _enc_hello(h: Hello) -> bytes:
    if len(h.mac) != 6:
        raise FrameError(f"mac 은 6 B, {len(h.mac)} B 받음")
    return bytes(h.mac) + bytes([_u8("fw", h.fw)]) + _u16("batt_mv", h.batt_mv)


def _dec_hello(b: bytes) -> Hello:
    r = _Reader(b, "HELLO"); mac = r.raw(6); fw = r.u8(); batt = r.u16(); r.done()
    return Hello(mac, fw, batt)


_register(P.Type.ACK, Ack, _enc_ack, _dec_ack)
_register(P.Type.STATUS, Status, _enc_status, _dec_status)
_register(P.Type.HELLO, Hello, _enc_hello, _dec_hello)
```

- [ ] **Step 4: 통과 확인**

Run: `cd lora_proto && uv run pytest -q`
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add lora_proto/lora_proto/codec.py lora_proto/tests/test_payloads.py
git commit -m "feat(proto): RESV·EXAM·CMD·SET_ROOM·ACK·STATUS·HELLO 페이로드 codec"
```

---

### Task 6: FILE — 레코드 스트림 · 청킹 · CRC16 · `build_file`

**Files:**
- Modify: `lora_proto/lora_proto/codec.py` (끝에 추가)
- Create: `lora_proto/tests/test_file.py`

**Interfaces:**
- Produces: `FileBegin(new_ver, kind, total_len, n_chunks)`, `FileData(seq, data: bytes)`, `FileEnd(crc16)`, `encode_records(records) -> bytes`, `decode_records(kind, body) -> list[SlotSet|ResvSet|ExamSet]`, `build_file(kind, records, new_ver) -> list[object]` (= `[FileBegin, FileData…, FileEnd]` 페이로드 객체 리스트. 프레임 조립은 호출자가 `encode_frame` + `encode_payload`로)
- 레코드 wire: `[recType u8][recLen u8][recPayload]`, recPayload = SLOT_SET/RESV_SET/EXAM_SET 본문 **NEW_VER 없이**. 레코드의 `new_ver` 필드는 무시된다(0으로 정규화)

- [ ] **Step 1: 실패하는 테스트**

`lora_proto/tests/test_file.py`:
```python
import pytest

from lora_proto import proto as P
from lora_proto.codec import (
    ExamSet, FileBegin, FileData, FileEnd, FrameError, ResvSet, SlotSet, build_file, crc16_ccitt,
    decode_payload, decode_records, encode_payload, encode_records,
)

S = [SlotSet(0, d, 9, 0, 10, 50, 1, f"과목{d}", "교수") for d in range(1, 6)]


def test_record_stream_layout():
    body = encode_records([S[0]])
    inner = encode_payload(S[0])[1:]                       # NEW_VER 제거한 본문
    assert body == bytes([P.Type.SLOT_SET, len(inner)]) + inner
    assert decode_records(P.FileKind.SCHEDULE, body) == [S[0]]


def test_records_ignore_new_ver_field():
    assert encode_records([SlotSet(7, 1, 9, 0, 10, 0, 1, "a", "b")]) == encode_records([SlotSet(0, 1, 9, 0, 10, 0, 1, "a", "b")])


def test_mixed_kind_records_rejected():
    with pytest.raises(FrameError):
        encode_records([S[0], ExamSet(0, 1, 2026, 1, 1, 2026, 1, 2)])
    with pytest.raises(FrameError):
        decode_records(P.FileKind.EXAM, encode_records([S[0]]))


def test_build_file_chunks_and_crc():
    records = [SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(30)]  # 40 B × 30
    body = encode_records(records)
    parts = build_file(P.FileKind.SCHEDULE, records, new_ver=9)
    begin, *datas, end = parts
    assert begin == FileBegin(new_ver=9, kind=P.FileKind.SCHEDULE, total_len=len(body), n_chunks=len(datas))
    assert all(len(d.data) <= P.FILE_CHUNK_MAX for d in datas)
    assert [d.seq for d in datas] == list(range(len(datas)))
    assert b"".join(d.data for d in datas) == body
    assert end == FileEnd(crc16=crc16_ccitt(body))
    assert len(datas) == -(-len(body) // P.FILE_CHUNK_MAX)


def test_file_payload_layouts():
    assert encode_payload(FileBegin(9, 1, 0x0123, 4)) == bytes([9, 1, 0x01, 0x23, 4])
    assert decode_payload(P.Type.FILE_BEGIN, bytes([9, 1, 0x01, 0x23, 4])) == FileBegin(9, 1, 0x123, 4)
    assert encode_payload(FileData(2, b"xyz")) == bytes([2]) + b"xyz"
    assert decode_payload(P.Type.FILE_DATA, bytes([2]) + b"xyz") == FileData(2, b"xyz")
    assert encode_payload(FileEnd(0x29B1)) == bytes([0x29, 0xB1])
    with pytest.raises(FrameError):
        encode_payload(FileData(0, bytes(201)))


def test_empty_file_is_one_begin_zero_data_one_end():
    parts = build_file(P.FileKind.RESV, [], new_ver=1)
    assert parts == [FileBegin(1, P.FileKind.RESV, 0, 0), FileEnd(crc16_ccitt(b""))]


def test_build_file_kind_must_match_records():
    with pytest.raises(FrameError):
        build_file(P.FileKind.RESV, S, new_ver=1)


def test_resv_and_exam_records_roundtrip():
    rs = [ResvSet(0, i, 2026, 11, 19, 13, 0, 15, 0, 6, "대관", "산학") for i in range(3)]
    assert decode_records(P.FileKind.RESV, encode_records(rs)) == rs
    es = [ExamSet(0, 1, 2026, 10, 20, 2026, 10, 24)]
    assert decode_records(P.FileKind.EXAM, encode_records(es)) == es
```

- [ ] **Step 2: 실패 확인**

Run: `cd lora_proto && uv run pytest tests/test_file.py -q`
Expected: FAIL — `ImportError: cannot import name 'FileBegin'`

- [ ] **Step 3: 구현** — `codec.py` 끝에 추가

```python
# ---------- FILE (§3.3) ----------

@dataclass(frozen=True)
class FileBegin:
    new_ver: int
    kind: int
    total_len: int
    n_chunks: int


@dataclass(frozen=True)
class FileData:
    seq: int
    data: bytes


@dataclass(frozen=True)
class FileEnd:
    crc16: int


_KIND_OF = {SlotSet: P.FileKind.SCHEDULE, ResvSet: P.FileKind.RESV, ExamSet: P.FileKind.EXAM}
_REC_TYPE = {P.FileKind.SCHEDULE: P.Type.SLOT_SET, P.FileKind.RESV: P.Type.RESV_SET, P.FileKind.EXAM: P.Type.EXAM_SET}
_REC_BODY = {SlotSet: _slot_body, ResvSet: _resv_body, ExamSet: _exam_body}
_REC_READ = {P.FileKind.SCHEDULE: _slot_read, P.FileKind.RESV: _resv_read, P.FileKind.EXAM: _exam_read}


def _kind_of_records(records: list) -> int | None:
    kinds = {_KIND_OF.get(type(r)) for r in records}
    if None in kinds:
        raise FrameError("FILE 레코드는 SlotSet/ResvSet/ExamSet 만 가능")
    if len(kinds) > 1:
        raise FrameError(f"한 FILE 에 kind 가 섞임: {sorted(kinds)}")
    return next(iter(kinds)) if kinds else None


def encode_records(records: list) -> bytes:
    """레코드 스트림: [recType][recLen][recPayload(NEW_VER 없음)] 반복. new_ver 필드는 무시."""
    kind = _kind_of_records(records)
    out = bytearray()
    for r in records:
        body = _REC_BODY[type(r)](r)
        if len(body) > 255:
            raise FrameError(f"레코드 {len(body)} B > 255")
        out += bytes([_REC_TYPE[kind], len(body)]) + body
    return bytes(out)


def decode_records(kind: int, body: bytes) -> list:
    if kind not in _REC_READ:
        raise FrameError(f"kind={kind} 는 1..3 밖")
    r = _Reader(body, "FILE body"); out = []
    while r.i < len(body):
        t = r.u8(); n = r.u8()
        if t != _REC_TYPE[kind]:
            raise FrameError(f"kind={kind} 파일에 recType {t:#x}")
        sub = _Reader(r.raw(n), "FILE record"); out.append(_REC_READ[kind](sub, 0)); sub.done()
    return out


def build_file(kind: int, records: list, new_ver: int) -> list:
    """FILE 세션 페이로드 목록: [FileBegin, FileData×n, FileEnd]. 프레임화는 호출자."""
    rk = _kind_of_records(records)
    if rk is not None and rk != kind:
        raise FrameError(f"kind={kind} 와 레코드 kind={rk} 불일치")
    body = encode_records(records)
    if len(body) > 0xFFFF:
        raise FrameError(f"FILE 본문 {len(body)} B > 65535")
    chunks = [body[i:i + P.FILE_CHUNK_MAX] for i in range(0, len(body), P.FILE_CHUNK_MAX)]
    if len(chunks) > 255:
        raise FrameError(f"청크 {len(chunks)} 개 > 255")
    return ([FileBegin(_u8("new_ver", new_ver), _u8("kind", kind, 1, 3), len(body), len(chunks))]
            + [FileData(i, c) for i, c in enumerate(chunks)]
            + [FileEnd(crc16_ccitt(body))])


def _enc_file_begin(f: FileBegin) -> bytes:
    return (bytes([_u8("new_ver", f.new_ver), _u8("kind", f.kind, 1, 3)]) + _u16("total_len", f.total_len)
            + bytes([_u8("n_chunks", f.n_chunks)]))


def _dec_file_begin(b: bytes) -> FileBegin:
    r = _Reader(b, "FILE_BEGIN"); nv = r.u8(); k = r.u8(); tl = r.u16(); n = r.u8(); r.done()
    return FileBegin(nv, _u8("kind", k, 1, 3), tl, n)


def _enc_file_data(f: FileData) -> bytes:
    if len(f.data) > P.FILE_CHUNK_MAX:
        raise FrameError(f"FILE_DATA {len(f.data)} B > {P.FILE_CHUNK_MAX}")
    return bytes([_u8("seq", f.seq)]) + bytes(f.data)


def _dec_file_data(b: bytes) -> FileData:
    r = _Reader(b, "FILE_DATA"); seq = r.u8(); data = r.raw(len(b) - 1)
    if len(data) > P.FILE_CHUNK_MAX:
        raise FrameError(f"FILE_DATA {len(data)} B > {P.FILE_CHUNK_MAX}")
    return FileData(seq, data)


def _dec_file_end(b: bytes) -> FileEnd:
    r = _Reader(b, "FILE_END"); v = FileEnd(r.u16()); r.done(); return v


_register(P.Type.FILE_BEGIN, FileBegin, _enc_file_begin, _dec_file_begin)
_register(P.Type.FILE_DATA, FileData, _enc_file_data, _dec_file_data)
_register(P.Type.FILE_END, FileEnd, lambda p: _u16("crc16", p.crc16), _dec_file_end)
```

- [ ] **Step 4: 통과 확인**

Run: `cd lora_proto && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 모두 PASS, ruff clean (포맷 지적이 있으면 `uv run ruff format .` 후 재확인)

- [ ] **Step 5: 커밋**

```bash
git add lora_proto/lora_proto/codec.py lora_proto/tests/test_file.py
git commit -m "feat(proto): FILE 레코드 스트림·청킹·CRC16·build_file"
```

---

### Task 7: `gen_vectors.py` → `test_vectors.json` + 드리프트 검사

**Files:**
- Create: `lora_proto/tools/gen_vectors.py`, `lora_proto/test_vectors.json` (생성물), `lora_proto/tests/test_vectors.py`

**Interfaces:**
- Produces: `gen_vectors.build() -> dict` (JSON 직렬화 가능), CLI `python -m tools.gen_vectors` (파일 갱신), `test_vectors.json` 스키마:
  ```json
  {"proto_ver": 2, "net_id": 75,
   "vectors": [{"name": "slot_set_basic",
                "header": {"type": 2, "bld": 69, "room": 301, "unit": 1, "txn": 7, "flags": 1},
                "payload": {"new_ver": 3, "day": 3, "s_h": 9, ...},
                "frame_hex": "21 4b 02 45 01 2d 01 07 …"}]}
  ```
  - `payload` 키는 Python dataclass 필드명 그대로. `bytes` 필드(`mac`, `args`, `data`)는 소문자 hex 문자열. `Status.ack`는 중첩 객체
  - `frame_hex`는 소문자 hex, 바이트 사이 공백 1개 (v2 §4.2 `frame` 형식과 동일)
  - 벡터 이름은 안정적이어야 한다(C++ 테스트 실패 메시지에 쓰임)

- [ ] **Step 1: 실패하는 테스트**

`lora_proto/tests/test_vectors.py`:
```python
import json
from pathlib import Path

from lora_proto import proto as P
from lora_proto.codec import decode_frame, decode_payload, encode_frame, encode_payload
from tools import gen_vectors
from tools.gen_vectors import from_json, to_json

VEC = Path(__file__).resolve().parents[1] / "test_vectors.json"


def test_committed_vectors_match_generator():
    """드리프트 검사: codec 이나 생성기를 바꿨으면 `uv run python -m tools.gen_vectors` 로 재생성해 같이 커밋한다."""
    assert VEC.exists(), "test_vectors.json 없음 — uv run python -m tools.gen_vectors"
    assert json.loads(VEC.read_text(encoding="utf-8")) == gen_vectors.build()


def test_every_type_covered_at_least_once():
    types = {v["header"]["type"] for v in gen_vectors.build()["vectors"]}
    assert types == {int(t) for t in P.Type}


def test_each_vector_roundtrips_through_codec():
    for v in gen_vectors.build()["vectors"]:
        frame = bytes.fromhex(v["frame_hex"].replace(" ", ""))
        h, pb = decode_frame(frame)
        assert (h.type, h.bld, h.room, h.unit, h.txn, h.flags) == tuple(v["header"][k] for k in ("type", "bld", "room", "unit", "txn", "flags")), v["name"]
        obj = decode_payload(h.type, pb)
        assert to_json(obj) == v["payload"], v["name"]
        assert encode_frame(h, encode_payload(from_json(h.type, v["payload"]))) == frame, v["name"]


def test_vectors_respect_size_limits():
    for v in gen_vectors.build()["vectors"]:
        assert len(bytes.fromhex(v["frame_hex"].replace(" ", ""))) <= P.MAX_FRAME, v["name"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd lora_proto && uv run pytest tests/test_vectors.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.gen_vectors'`

- [ ] **Step 3: 구현**

`lora_proto/tools/gen_vectors.py`:
```python
"""test_vectors.json 생성기. Python codec 이 만든 프레임을 C++ Unity 테스트가 바이트 단위로 재검증한다.
실행: uv run python -m tools.gen_vectors  (lora_proto/ 에서)"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from lora_proto import proto as P
from lora_proto import codec as C

OUT = Path(__file__).resolve().parents[1] / "test_vectors.json"
_CLASSES = {
    P.Type.TIME: C.Time, P.Type.SLOT_SET: C.SlotSet, P.Type.SLOT_DEL: C.SlotDel, P.Type.DAY_CLEAR: C.DayClear,
    P.Type.RESV_SET: C.ResvSet, P.Type.RESV_DEL: C.ResvDel, P.Type.EXAM_SET: C.ExamSet, P.Type.EXAM_DEL: C.ExamDel,
    P.Type.FILE_BEGIN: C.FileBegin, P.Type.FILE_DATA: C.FileData, P.Type.FILE_END: C.FileEnd, P.Type.CMD: C.Cmd,
    P.Type.SET_ROOM: C.SetRoom, P.Type.ACK: C.Ack, P.Type.STATUS: C.Status, P.Type.HELLO: C.Hello,
}


def to_json(obj: object) -> dict:
    """dataclass → JSON dict. bytes 는 hex 문자열, 중첩 dataclass 는 재귀."""
    out = {}
    for f in dataclasses.fields(obj):
        v = getattr(obj, f.name)
        out[f.name] = v.hex() if isinstance(v, bytes) else to_json(v) if dataclasses.is_dataclass(v) else int(v)
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
        "header": {"type": int(h.type), "bld": h.bld, "room": h.room, "unit": h.unit, "txn": h.txn, "flags": h.flags},
        "payload": to_json(payload),
        "frame_hex": _hex(frame),
    }


E, A = ord("E"), ord("A")
MAC = bytes.fromhex("a0b1c2d3e4f5")


def build() -> dict:
    T = P.Type
    slot = C.SlotSet(3, 3, 9, 0, 10, 50, P.SlotType.CLASS, "임베디드시스템", "정필성")
    slot_max = C.SlotSet(255, 7, 23, 59, 23, 59, P.SlotType.RENTAL, "가" * 6 + "ab", "가" * 4)
    resv = C.ResvSet(2, 0x0102, 2026, 11, 19, 13, 0, 15, 0, P.SlotType.RENTAL, "경진대회", "산학처")
    exam = C.ExamSet(4, 7, 2026, 10, 20, 2026, 10, 24)
    ack = C.Ack(P.AckStatus.OK, 0, 3987, 12, 3, 1, 1, 20, P.Layout.CLASS)
    big_records = [C.SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(12)]  # 40 B × 12 = 480 B → 3 청크
    fb, fd0, fd1, fd2, fe = C.build_file(P.FileKind.SCHEDULE, big_records, new_ver=9)
    assert fd2.seq == 2 and len(fd0.data) == P.FILE_CHUNK_MAX

    def H(t, bld=E, room=301, unit=1, txn=7, flags=P.FLAG_ACK_REQ):
        return C.Header(type=t, bld=bld, room=room, unit=unit, txn=txn, flags=flags)

    vectors = [
        _vec("time_broadcast", H(T.TIME, P.BLD_ALL, P.ROOM_ALL, 0, 0, P.FLAG_BROADCAST | P.FLAG_WAKE_SENT), C.Time(1_757_400_000, P.TimeFlag.REQUEST_STATUS)),
        _vec("time_targeted_resync", H(T.TIME, flags=P.FLAG_WAKE_SENT, txn=0), C.Time(1_757_403_600, 0)),
        _vec("slot_set_basic", H(T.SLOT_SET), slot),
        _vec("slot_set_max_strings_ver255", H(T.SLOT_SET, txn=255), slot_max),
        _vec("slot_set_unit0_all_units", H(T.SLOT_SET, unit=0, txn=1), C.SlotSet(1, 1, 9, 0, 10, 0, 1, "s", "p")),
        _vec("slot_del", H(T.SLOT_DEL, txn=8), C.SlotDel(4, 3, 9, 0)),
        _vec("day_clear", H(T.DAY_CLEAR, txn=9), C.DayClear(5, 3)),
        _vec("resv_set_rental", H(T.RESV_SET, txn=10), resv),
        _vec("resv_set_ascii", H(T.RESV_SET, A, 1, 2, 11), C.ResvSet(1, 1, 2026, 1, 1, 0, 0, 23, 59, P.SlotType.CANCELLED, "abc", "xy")),
        _vec("resv_del", H(T.RESV_DEL, txn=12), C.ResvDel(3, 0x0102)),
        _vec("exam_set", H(T.EXAM_SET, txn=13), exam),
        _vec("exam_del", H(T.EXAM_DEL, txn=14), C.ExamDel(5, 7)),
        _vec("file_begin_schedule_3chunks", H(T.FILE_BEGIN, txn=15), fb),
        _vec("file_data_seq0_full_200B", H(T.FILE_DATA, txn=16), fd0),
        _vec("file_data_seq2_tail", H(T.FILE_DATA, txn=18), fd2),
        _vec("file_end", H(T.FILE_END, txn=19), fe),
        _vec("file_begin_empty_resv", H(T.FILE_BEGIN, txn=20), C.FileBegin(1, P.FileKind.RESV, 0, 0)),
        _vec("cmd_reboot", H(T.CMD, txn=21), C.Cmd(P.Cmd.REBOOT)),
        _vec("cmd_test_render_layout7", H(T.CMD, txn=22), C.Cmd(P.Cmd.TEST_RENDER, bytes([P.Layout.RENTAL]))),
        _vec("cmd_set_param_status_hour", H(T.CMD, txn=23), C.Cmd(P.Cmd.SET_PARAM, bytes([1]) + (18).to_bytes(4, "big"))),
        _vec("set_room_provision", H(T.SET_ROOM, P.BLD_UNPROVISIONED, 0, 0, 24), C.SetRoom(1, MAC, E, 301, 2)),
        _vec("ack_ok", H(T.ACK, txn=7, flags=0), ack),
        _vec("ack_gap", H(T.ACK, txn=8, flags=0), dataclasses.replace(ack, status=P.AckStatus.GAP, sched_ver=11)),
        _vec("ack_file_missing_seq3", H(T.ACK, txn=16, flags=0), dataclasses.replace(ack, status=P.AckStatus.FILE_MISSING, detail=3)),
        _vec("status_daily", H(T.STATUS, txn=0, flags=0), C.Status(ack, -97, -6, P.StatusFlag.LOW_BATT, 300)),
        _vec("status_clock_stale_positive_snr", H(T.STATUS, txn=0, flags=0), C.Status(ack, -60, 38, P.StatusFlag.CLOCK_STALE, 0)),
        _vec("hello_unprovisioned", H(T.HELLO, P.BLD_UNPROVISIONED, 0, 0, 0, 0), C.Hello(MAC, 20, 4100)),
    ]
    return {"proto_ver": P.PROTO_VER, "net_id": P.NET_ID, "vectors": vectors}


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(build()['vectors'])} vectors)")
    sys.exit(0)
```

- [ ] **Step 4: 벡터 생성 후 통과 확인**

Run: `cd lora_proto && uv run python -m tools.gen_vectors && uv run pytest -q`
Expected: `wrote …/test_vectors.json (27 vectors)` 그리고 모두 PASS

`test_vectors.json`을 열어 `slot_set_basic`의 `frame_hex`가 `21 4b 02 45 01 2d 01 07 …`로 시작하는지 눈으로 확인한다(헤더 9 B: VER_FLAGS 0x21, NET_ID 0x4b, TYPE 0x02, BLD 'E'=0x45, ROOM 301=0x012d, UNIT 1, TXN 7, LEN).

- [ ] **Step 5: 커밋**

```bash
git add lora_proto/tools/gen_vectors.py lora_proto/test_vectors.json lora_proto/tests/test_vectors.py
git commit -m "feat(proto): 테스트 벡터 생성기와 test_vectors.json (27 벡터, 전 TYPE)"
```

---

### Task 8: firmware — PlatformIO `[env:native]` + `.clang-format` + C++ CRC·헤더 codec + Unity 헤더 벡터 테스트

**Files:**
- Create: `firmware/platformio.ini`, `.clang-format` (리포 루트), `firmware/lib/lora_codec/lora_codec.h`, `firmware/lib/lora_codec/lora_codec.cpp`, `firmware/test/test_codec/test_main.cpp`, `firmware/test/test_codec/vectors_path.h`
- Modify: `.github/workflows/ci.yml` (firmware lint 명령 — 아래)

**Interfaces:**
- Produces (`namespace lc`): `uint8_t crc8(const uint8_t*, size_t)`, `uint16_t crc16(const uint8_t*, size_t)`, `struct Header {uint8_t ver, flags, netId, type, bld; uint16_t room; uint8_t unit, txn, len;}`, `size_t encodeFrame(const Header&, const uint8_t* payload, uint8_t len, uint8_t* out, size_t cap)` (0 = 실패), `bool decodeFrame(const uint8_t* buf, size_t len, Header& h, const uint8_t*& payload, uint8_t netId = RP_NET_ID)`, `bool matchesAck(const Header& req, const Header& rx)`
- `lora_proto/proto.h`·`radio_params.h`는 `platformio.ini`의 `build_flags = -I../lora_proto`로 include

- [ ] **Step 1: 실패하는 테스트**

`firmware/test/test_codec/vectors_path.h`:
```cpp
#pragma once
// PlatformIO native 테스트는 firmware/ 를 CWD 로 실행한다.
#define LC_VECTORS_PATH "../lora_proto/test_vectors.json"
```

`firmware/test/test_codec/test_main.cpp` (이 Task 분량 — Task 9에서 페이로드 검사를 추가):
```cpp
#include <ArduinoJson.h>
#include <unity.h>

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "lora_codec.h"
#include "vectors_path.h"

static JsonDocument g_doc;

static std::vector<uint8_t> fromHex(const char* s) {
  std::vector<uint8_t> out;
  unsigned v;
  while (*s) {
    if (*s == ' ') { ++s; continue; }
    if (sscanf(s, "%2x", &v) != 1) break;
    out.push_back((uint8_t)v);
    s += 2;
  }
  return out;
}

static void loadVectors() {
  FILE* f = fopen(LC_VECTORS_PATH, "rb");
  TEST_ASSERT_NOT_NULL_MESSAGE(f, "test_vectors.json 열기 실패 — lora_proto/ 에서 uv run python -m tools.gen_vectors");
  std::string s; char buf[4096]; size_t n;
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) s.append(buf, n);
  fclose(f);
  TEST_ASSERT_TRUE_MESSAGE(deserializeJson(g_doc, s) == DeserializationError::Ok, "JSON 파싱 실패");
}

void test_crc8_known() {
  const uint8_t d[] = "123456789";
  TEST_ASSERT_EQUAL_HEX8(0xF4, lc::crc8(d, 9));
  TEST_ASSERT_EQUAL_HEX8(0x00, lc::crc8(d, 0));
}

void test_crc16_known() {
  const uint8_t d[] = "123456789";
  TEST_ASSERT_EQUAL_HEX16(0x29B1, lc::crc16(d, 9));
  TEST_ASSERT_EQUAL_HEX16(0xFFFF, lc::crc16(d, 0));
}

void test_every_vector_header_decodes_and_reencodes() {
  for (JsonObject v : g_doc["vectors"].as<JsonArray>()) {
    const char* name = v["name"];
    std::vector<uint8_t> frame = fromHex(v["frame_hex"]);
    lc::Header h; const uint8_t* pl = nullptr;
    TEST_ASSERT_TRUE_MESSAGE(lc::decodeFrame(frame.data(), frame.size(), h, pl), name);
    JsonObject jh = v["header"];
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["type"], h.type, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["bld"], h.bld, name);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(jh["room"], h.room, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["unit"], h.unit, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["txn"], h.txn, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["flags"], h.flags, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(LP_PROTO_VER, h.ver, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(RP_NET_ID, h.netId, name);
    uint8_t out[LP_MAX_FRAME];
    size_t n = lc::encodeFrame(h, pl, h.len, out, sizeof out);
    TEST_ASSERT_EQUAL_MESSAGE(frame.size(), n, name);
    TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(frame.data(), out, n, name);
  }
}

void test_bad_frames_rejected() {
  std::vector<uint8_t> f = fromHex(g_doc["vectors"][2]["frame_hex"]);  // slot_set_basic
  lc::Header h; const uint8_t* pl;
  std::vector<uint8_t> a = f; a.back() ^= 0xFF;                       // CRC
  TEST_ASSERT_FALSE(lc::decodeFrame(a.data(), a.size(), h, pl));
  std::vector<uint8_t> b = f; b[1] = 0x00;                            // NET_ID
  TEST_ASSERT_FALSE(lc::decodeFrame(b.data(), b.size(), h, pl));
  std::vector<uint8_t> c = f; c[0] = 0x31;                            // ver 3
  TEST_ASSERT_FALSE(lc::decodeFrame(c.data(), c.size(), h, pl));
  std::vector<uint8_t> d = f; d[8] = 9;                               // LEN 불일치
  TEST_ASSERT_FALSE(lc::decodeFrame(d.data(), d.size(), h, pl));
  TEST_ASSERT_FALSE(lc::decodeFrame(f.data(), 5, h, pl));              // 짧음
}

void test_matches_ack() {
  lc::Header req{LP_PROTO_VER, LP_FLAG_ACK_REQ, RP_NET_ID, LP_TYPE_SLOT_SET, 'E', 301, 1, 7, 0};
  lc::Header ack{LP_PROTO_VER, 0, RP_NET_ID, LP_TYPE_ACK, 'E', 301, 1, 7, 0};
  TEST_ASSERT_TRUE(lc::matchesAck(req, ack));
  ack.txn = 8;
  TEST_ASSERT_FALSE(lc::matchesAck(req, ack));
  ack.txn = 7; ack.type = LP_TYPE_STATUS;
  TEST_ASSERT_FALSE(lc::matchesAck(req, ack));
}

int main() {
  UNITY_BEGIN();
  loadVectors();
  RUN_TEST(test_crc8_known);
  RUN_TEST(test_crc16_known);
  RUN_TEST(test_every_vector_header_decodes_and_reencodes);
  RUN_TEST(test_bad_frames_rejected);
  RUN_TEST(test_matches_ack);
  return UNITY_END();
}
```

- [ ] **Step 2: 실패 확인**

`firmware/platformio.ini`:
```ini
; Woo-ESC-Capston 펌웨어. [env:terminal](노드) 와 [env:modem] 은 S7·S8 에서 추가한다.
[platformio]
default_envs = native

[env]
build_flags = -std=c++17 -Wall -Wextra -I../lora_proto
lib_deps =
    bblanchon/ArduinoJson@^7.2.0

; 호스트 테스트: codec · determineLayout · nextChangeAt · 렌더 프리뷰
[env:native]
platform = native
test_framework = unity
build_flags = ${env.build_flags} -DLC_NATIVE
```

Run: `cd firmware && pio test -e native -v`
Expected: 컴파일 실패 — `lora_codec.h: No such file or directory`

- [ ] **Step 3: 구현**

`.clang-format` (리포 루트):
```yaml
BasedOnStyle: Google
IndentWidth: 2
ColumnLimit: 110
AllowShortFunctionsOnASingleLine: Inline
DerivePointerAlignment: false
PointerAlignment: Left
```

`firmware/lib/lora_codec/lora_codec.h` (이 Task 분량 — Task 9에서 페이로드 선언을 추가):
```cpp
#pragma once
// 공중 프레임 v2 codec — 하드웨어 의존 없음. 상수는 lora_proto/proto.h 가 원본.
#include <stddef.h>
#include <stdint.h>

#include "proto.h"
#include "radio_params.h"

namespace lc {

uint8_t crc8(const uint8_t* d, size_t n);    // poly 0x07 init 0
uint16_t crc16(const uint8_t* d, size_t n);  // CCITT-FALSE

struct Header {
  uint8_t ver, flags, netId, type, bld;
  uint16_t room;
  uint8_t unit, txn, len;
};

// 성공 시 총 길이(헤더+페이로드+CRC), 실패 시 0. cap 은 out 버퍼 크기.
size_t encodeFrame(const Header& h, const uint8_t* payload, uint8_t len, uint8_t* out, size_t cap);
// 성공 시 h 채우고 payload 는 buf 안을 가리킴(복사 없음).
bool decodeFrame(const uint8_t* buf, size_t n, Header& h, const uint8_t*& payload, uint8_t netId = RP_NET_ID);
// v2 §4.4: NET_ID·TYPE==ACK·BLD/ROOM/UNIT/TXN 일치
bool matchesAck(const Header& req, const Header& rx);

}  // namespace lc
```

`firmware/lib/lora_codec/lora_codec.cpp` (이 Task 분량):
```cpp
#include "lora_codec.h"

namespace lc {

uint8_t crc8(const uint8_t* d, size_t n) {
  uint8_t c = 0;
  for (size_t i = 0; i < n; ++i) {
    c ^= d[i];
    for (int b = 0; b < 8; ++b) c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
  }
  return c;
}

uint16_t crc16(const uint8_t* d, size_t n) {
  uint16_t c = 0xFFFF;
  for (size_t i = 0; i < n; ++i) {
    c ^= (uint16_t)d[i] << 8;
    for (int b = 0; b < 8; ++b) c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
  }
  return c;
}

size_t encodeFrame(const Header& h, const uint8_t* payload, uint8_t len, uint8_t* out, size_t cap) {
  if (len > LP_MAX_PAYLOAD || (h.flags & 0xF0) || h.ver > 15) return 0;
  size_t total = LP_HEADER_LEN + len + 1;
  if (cap < total) return 0;
  out[0] = (uint8_t)((h.ver << 4) | (h.flags & 0x0F));
  out[1] = h.netId;
  out[2] = h.type;
  out[3] = h.bld;
  out[4] = (uint8_t)(h.room >> 8);
  out[5] = (uint8_t)(h.room & 0xFF);
  out[6] = h.unit;
  out[7] = h.txn;
  out[8] = len;
  for (uint8_t i = 0; i < len; ++i) out[LP_HEADER_LEN + i] = payload[i];
  out[total - 1] = crc8(out, total - 1);
  return total;
}

bool decodeFrame(const uint8_t* buf, size_t n, Header& h, const uint8_t*& payload, uint8_t netId) {
  if (n < LP_HEADER_LEN + 1) return false;
  if ((buf[0] >> 4) != LP_PROTO_VER) return false;
  if (buf[1] != netId) return false;
  uint8_t len = buf[8];
  if (n != (size_t)LP_HEADER_LEN + len + 1) return false;
  if (crc8(buf, n - 1) != buf[n - 1]) return false;
  h.ver = buf[0] >> 4;
  h.flags = buf[0] & 0x0F;
  h.netId = buf[1];
  h.type = buf[2];
  h.bld = buf[3];
  h.room = (uint16_t)((buf[4] << 8) | buf[5]);
  h.unit = buf[6];
  h.txn = buf[7];
  h.len = len;
  payload = buf + LP_HEADER_LEN;
  return true;
}

bool matchesAck(const Header& req, const Header& rx) {
  return rx.type == LP_TYPE_ACK && rx.netId == req.netId && rx.bld == req.bld && rx.room == req.room &&
         rx.unit == req.unit && rx.txn == req.txn;
}

}  // namespace lc
```

CI의 firmware lint 단계는 `[env:terminal]`·`[env:modem]`이 아직 없어 실패하므로 `.github/workflows/ci.yml`의 firmware `lint` 스텝을 다음으로 바꾼다 (env 인자 제거 → `platformio.ini`에 있는 env 전부 검사):
```yaml
      - name: lint
        if: steps.manifest.outputs.ready == 'true'
        run: pio check --fail-on-defect medium --fail-on-defect high
```

- [ ] **Step 4: 통과 확인**

Run: `cd firmware && pio test -e native && pio check --fail-on-defect medium --fail-on-defect high && clang-format --dry-run --Werror lib/lora_codec/*.h lib/lora_codec/*.cpp test/test_codec/*.cpp`
Expected: `5 test cases: 5 succeeded`, cppcheck 결함 0, clang-format 출력 없음 (지적이 있으면 `clang-format -i <파일>` 후 재확인)

- [ ] **Step 5: 커밋**

```bash
git add .clang-format firmware/platformio.ini firmware/lib/lora_codec firmware/test/test_codec .github/workflows/ci.yml
git commit -m "feat(firmware): PlatformIO native env, C++ CRC·헤더 codec, 벡터 헤더 라운드트립 테스트"
```

---

### Task 9: C++ 페이로드 codec 전체 + 벡터 필드·재인코딩 검증

**Files:**
- Modify: `firmware/lib/lora_codec/lora_codec.h`, `firmware/lib/lora_codec/lora_codec.cpp`, `firmware/test/test_codec/test_main.cpp`

**Interfaces:**
- Produces (`namespace lc`): 구조체 `Time, SlotRec, SlotDel, DayClear, ResvRec, ResvDel, ExamRec, ExamDel, FileBegin, FileData, FileEnd, CmdMsg, SetRoom, Ack, Status, Hello` 와 각 `size_t enc<X>(…, uint8_t* out, size_t cap)` (0 = 실패) / `bool dec<X>(const uint8_t* p, uint8_t n, …)`. NEW_VER 를 갖는 타입은 `enc(uint8_t newVer, const X&, out, cap)` / `dec(p, n, uint8_t& newVer, X&)`.
- FILE 본문 순회: `bool nextRecord(const uint8_t* body, uint16_t n, uint16_t& pos, uint8_t& recType, const uint8_t*& rec, uint8_t& recLen)` + `decSlotBody / decResvBody / decExamBody(rec, recLen, X&)`. 노드 펌웨어(S8)가 `/schedule.bin` 등을 이 함수로 읽는다.
- 문자열은 NUL 종단 `char subj[LP_SUBJ_MAX + 1]`, `char prof[LP_PROF_MAX + 1]`. 연도는 wire 값(`year-2000`) 그대로 `uint8_t y`.

- [ ] **Step 1: 실패하는 테스트** — `test_main.cpp`에 추가

`fromHex` 아래에 헬퍼를, `main()` 앞에 테스트를 추가:
```cpp
static void expectStr(const char* name, const char* expect, const char* got) {
  TEST_ASSERT_EQUAL_STRING_MESSAGE(expect, got, name);
}

static void checkSlot(const char* name, JsonObject j, const lc::SlotRec& s) {
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], s.day, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_h"], s.sH, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_m"], s.sM, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["e_h"], s.eH, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["e_m"], s.eM, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["type"], s.type, name);
  expectStr(name, j["subject"], s.subj);
  expectStr(name, j["professor"], s.prof);
}

static void checkResv(const char* name, JsonObject j, const lc::ResvRec& r) {
  TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["resv_id"], r.resvId, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE((int)j["year"] - 2000, r.y, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["month"], r.m, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], r.d, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_h"], r.sH, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["e_m"], r.eM, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["type"], r.type, name);
  expectStr(name, j["subject"], r.subj);
  expectStr(name, j["professor"], r.prof);
}

static void checkAck(const char* name, JsonObject j, const lc::Ack& a) {
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["status"], a.status, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["detail"], a.detail, name);
  TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["batt_mv"], a.battMv, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["sched_ver"], a.schedVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["resv_ver"], a.resvVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["exam_ver"], a.examVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["ident_ver"], a.identVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["fw"], a.fw, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["layout"], a.layout, name);
}

static void checkMac(const char* name, const char* hex, const uint8_t* mac) {
  std::vector<uint8_t> m = fromHex(hex);
  TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(m.data(), mac, 6, name);
}

// 각 벡터: 디코드 → JSON 필드 대조 → 재인코딩 → 원 페이로드 바이트와 대조
void test_every_vector_payload_decodes_and_reencodes() {
  for (JsonObject v : g_doc["vectors"].as<JsonArray>()) {
    const char* name = v["name"];
    std::vector<uint8_t> frame = fromHex(v["frame_hex"]);
    lc::Header h; const uint8_t* pl;
    TEST_ASSERT_TRUE(lc::decodeFrame(frame.data(), frame.size(), h, pl));
    JsonObject j = v["payload"];
    uint8_t out[LP_MAX_PAYLOAD]; size_t n = 0; uint8_t nv = 0;
    switch (h.type) {
      case LP_TYPE_TIME: { lc::Time t; TEST_ASSERT_TRUE_MESSAGE(lc::decTime(pl, h.len, t), name);
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(j["epoch"], t.epoch, name); TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["flags"], t.flags, name);
        n = lc::encTime(t, out, sizeof out); break; }
      case LP_TYPE_SLOT_SET: { lc::SlotRec s; TEST_ASSERT_TRUE_MESSAGE(lc::decSlotSet(pl, h.len, nv, s), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["new_ver"], nv, name); checkSlot(name, j, s);
        n = lc::encSlotSet(nv, s, out, sizeof out); break; }
      case LP_TYPE_SLOT_DEL: { lc::SlotDel s; TEST_ASSERT_TRUE_MESSAGE(lc::decSlotDel(pl, h.len, nv, s), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], s.day, name); TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_m"], s.sM, name);
        n = lc::encSlotDel(nv, s, out, sizeof out); break; }
      case LP_TYPE_DAY_CLEAR: { lc::DayClear d; TEST_ASSERT_TRUE_MESSAGE(lc::decDayClear(pl, h.len, nv, d), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], d.day, name);
        n = lc::encDayClear(nv, d, out, sizeof out); break; }
      case LP_TYPE_RESV_SET: { lc::ResvRec r; TEST_ASSERT_TRUE_MESSAGE(lc::decResvSet(pl, h.len, nv, r), name);
        checkResv(name, j, r); n = lc::encResvSet(nv, r, out, sizeof out); break; }
      case LP_TYPE_RESV_DEL: { lc::ResvDel r; TEST_ASSERT_TRUE_MESSAGE(lc::decResvDel(pl, h.len, nv, r), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["resv_id"], r.resvId, name);
        n = lc::encResvDel(nv, r, out, sizeof out); break; }
      case LP_TYPE_EXAM_SET: { lc::ExamRec e; TEST_ASSERT_TRUE_MESSAGE(lc::decExamSet(pl, h.len, nv, e), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["exam_id"], e.examId, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE((int)j["y2"] - 2000, e.y2, name); TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["d2"], e.d2, name);
        n = lc::encExamSet(nv, e, out, sizeof out); break; }
      case LP_TYPE_EXAM_DEL: { lc::ExamDel e; TEST_ASSERT_TRUE_MESSAGE(lc::decExamDel(pl, h.len, nv, e), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["exam_id"], e.examId, name);
        n = lc::encExamDel(nv, e, out, sizeof out); break; }
      case LP_TYPE_FILE_BEGIN: { lc::FileBegin f; TEST_ASSERT_TRUE_MESSAGE(lc::decFileBegin(pl, h.len, nv, f), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["kind"], f.kind, name); TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["total_len"], f.totalLen, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["n_chunks"], f.nChunks, name);
        n = lc::encFileBegin(nv, f, out, sizeof out); break; }
      case LP_TYPE_FILE_DATA: { lc::FileData f; TEST_ASSERT_TRUE_MESSAGE(lc::decFileData(pl, h.len, f), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["seq"], f.seq, name);
        std::vector<uint8_t> d = fromHex(j["data"]); TEST_ASSERT_EQUAL_MESSAGE(d.size(), f.len, name);
        TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(d.data(), f.data, d.size(), name);
        n = lc::encFileData(f, out, sizeof out); break; }
      case LP_TYPE_FILE_END: { lc::FileEnd f; TEST_ASSERT_TRUE_MESSAGE(lc::decFileEnd(pl, h.len, f), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["crc16"], f.crc, name);
        n = lc::encFileEnd(f, out, sizeof out); break; }
      case LP_TYPE_CMD: { lc::CmdMsg c; TEST_ASSERT_TRUE_MESSAGE(lc::decCmd(pl, h.len, c), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["cmd"], c.cmd, name);
        std::vector<uint8_t> a = fromHex(j["args"]); TEST_ASSERT_EQUAL_MESSAGE(a.size(), c.argsLen, name);
        n = lc::encCmd(c, out, sizeof out); break; }
      case LP_TYPE_SET_ROOM: { lc::SetRoom s; TEST_ASSERT_TRUE_MESSAGE(lc::decSetRoom(pl, h.len, nv, s), name);
        checkMac(name, j["mac"], s.mac); TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["bld"], s.bld, name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["room"], s.room, name); TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["unit"], s.unit, name);
        n = lc::encSetRoom(nv, s, out, sizeof out); break; }
      case LP_TYPE_ACK: { lc::Ack a; TEST_ASSERT_TRUE_MESSAGE(lc::decAck(pl, h.len, a), name);
        checkAck(name, j, a); n = lc::encAck(a, out, sizeof out); break; }
      case LP_TYPE_STATUS: { lc::Status s; TEST_ASSERT_TRUE_MESSAGE(lc::decStatus(pl, h.len, s), name);
        checkAck(name, j["ack"], s.ack);
        TEST_ASSERT_EQUAL_INT8_MESSAGE(j["rssi_last"], s.rssiLast, name); TEST_ASSERT_EQUAL_INT8_MESSAGE(j["snr_last_x4"], s.snrLastX4, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["flags"], s.flags, name); TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["uptime_h"], s.uptimeH, name);
        n = lc::encStatus(s, out, sizeof out); break; }
      case LP_TYPE_HELLO: { lc::Hello hl; TEST_ASSERT_TRUE_MESSAGE(lc::decHello(pl, h.len, hl), name);
        checkMac(name, j["mac"], hl.mac); TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["fw"], hl.fw, name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["batt_mv"], hl.battMv, name);
        n = lc::encHello(hl, out, sizeof out); break; }
      default: TEST_FAIL_MESSAGE(name);
    }
    TEST_ASSERT_EQUAL_MESSAGE(h.len, n, name);
    TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(pl, out, n, name);
  }
}

void test_string_over_limit_rejected() {
  // 구조체 버퍼(LP_SUBJ_MAX+1)에는 21 B 를 담을 수 없으므로 디코더 쪽 한계만 검사: subjLen=21 인 바이트열
  uint8_t bad[] = {1, 3, 9, 0, 10, 0, 1, 21, 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a',
                   'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 1, 'p'};
  uint8_t nv; lc::SlotRec d;
  TEST_ASSERT_FALSE(lc::decSlotSet(bad, sizeof bad, nv, d));
  // 인코더 쪽: 범위 밖 필드(day=8)는 0 을 돌려준다
  lc::SlotRec s{8, 9, 0, 10, 0, 1, "s", "p"};
  uint8_t out[LP_MAX_PAYLOAD];
  TEST_ASSERT_EQUAL(0, lc::encSlotSet(1, s, out, sizeof out));
}

void test_file_records_iterate() {
  // file_data_seq0_full_200B 의 data 는 40 B 레코드 5개
  JsonObject v = g_doc["vectors"][13];
  std::vector<uint8_t> body = fromHex(v["payload"]["data"]);
  uint16_t pos = 0; uint8_t rt; const uint8_t* rec; uint8_t rl; int count = 0;
  while (lc::nextRecord(body.data(), (uint16_t)body.size(), pos, rt, rec, rl)) {
    TEST_ASSERT_EQUAL_UINT8(LP_TYPE_SLOT_SET, rt);
    lc::SlotRec s; TEST_ASSERT_TRUE(lc::decSlotBody(rec, rl, s));
    TEST_ASSERT_EQUAL_UINT8(1 + count % 7, s.day);
    ++count;
  }
  TEST_ASSERT_EQUAL(5, count);
  TEST_ASSERT_EQUAL(body.size(), pos);
}
```
`main()`에 추가:
```cpp
  RUN_TEST(test_every_vector_payload_decodes_and_reencodes);
  RUN_TEST(test_string_over_limit_rejected);
  RUN_TEST(test_file_records_iterate);
```

- [ ] **Step 2: 실패 확인**

Run: `cd firmware && pio test -e native`
Expected: 컴파일 실패 — `'Time' is not a member of 'lc'`

- [ ] **Step 3: 구현**

`lora_codec.h`의 `matchesAck` 선언 아래, `}  // namespace lc` 앞에 추가:
```cpp
// ---------- §3.3 페이로드 구조체 ----------
struct Time { uint32_t epoch; uint8_t flags; };
struct SlotRec { uint8_t day, sH, sM, eH, eM, type; char subj[LP_SUBJ_MAX + 1]; char prof[LP_PROF_MAX + 1]; };
struct SlotDel { uint8_t day, sH, sM; };
struct DayClear { uint8_t day; };
struct ResvRec { uint16_t resvId; uint8_t y, m, d, sH, sM, eH, eM, type; char subj[LP_SUBJ_MAX + 1]; char prof[LP_PROF_MAX + 1]; };
struct ResvDel { uint16_t resvId; };
struct ExamRec { uint16_t examId; uint8_t y1, m1, d1, y2, m2, d2; };
struct ExamDel { uint16_t examId; };
struct FileBegin { uint8_t kind; uint16_t totalLen; uint8_t nChunks; };
struct FileData { uint8_t seq; const uint8_t* data; uint8_t len; };
struct FileEnd { uint16_t crc; };
struct CmdMsg { uint8_t cmd; const uint8_t* args; uint8_t argsLen; };
struct SetRoom { uint8_t mac[6]; uint8_t bld; uint16_t room; uint8_t unit; };
struct Ack { uint8_t status, detail; uint16_t battMv; uint8_t schedVer, resvVer, examVer, identVer, fw, layout; };
struct Status { Ack ack; int8_t rssiLast, snrLastX4; uint8_t flags; uint16_t uptimeH; };
struct Hello { uint8_t mac[6]; uint8_t fw; uint16_t battMv; };

// enc*: 성공 시 길이, 실패(범위·cap) 시 0.  dec*: 길이·범위·잔여 바이트 검사, 실패 시 false.
size_t encTime(const Time&, uint8_t* out, size_t cap);
bool decTime(const uint8_t* p, uint8_t n, Time&);
size_t encSlotSet(uint8_t newVer, const SlotRec&, uint8_t* out, size_t cap);
bool decSlotSet(const uint8_t* p, uint8_t n, uint8_t& newVer, SlotRec&);
size_t encSlotDel(uint8_t newVer, const SlotDel&, uint8_t* out, size_t cap);
bool decSlotDel(const uint8_t* p, uint8_t n, uint8_t& newVer, SlotDel&);
size_t encDayClear(uint8_t newVer, const DayClear&, uint8_t* out, size_t cap);
bool decDayClear(const uint8_t* p, uint8_t n, uint8_t& newVer, DayClear&);
size_t encResvSet(uint8_t newVer, const ResvRec&, uint8_t* out, size_t cap);
bool decResvSet(const uint8_t* p, uint8_t n, uint8_t& newVer, ResvRec&);
size_t encResvDel(uint8_t newVer, const ResvDel&, uint8_t* out, size_t cap);
bool decResvDel(const uint8_t* p, uint8_t n, uint8_t& newVer, ResvDel&);
size_t encExamSet(uint8_t newVer, const ExamRec&, uint8_t* out, size_t cap);
bool decExamSet(const uint8_t* p, uint8_t n, uint8_t& newVer, ExamRec&);
size_t encExamDel(uint8_t newVer, const ExamDel&, uint8_t* out, size_t cap);
bool decExamDel(const uint8_t* p, uint8_t n, uint8_t& newVer, ExamDel&);
size_t encFileBegin(uint8_t newVer, const FileBegin&, uint8_t* out, size_t cap);
bool decFileBegin(const uint8_t* p, uint8_t n, uint8_t& newVer, FileBegin&);
size_t encFileData(const FileData&, uint8_t* out, size_t cap);
bool decFileData(const uint8_t* p, uint8_t n, FileData&);
size_t encFileEnd(const FileEnd&, uint8_t* out, size_t cap);
bool decFileEnd(const uint8_t* p, uint8_t n, FileEnd&);
size_t encCmd(const CmdMsg&, uint8_t* out, size_t cap);
bool decCmd(const uint8_t* p, uint8_t n, CmdMsg&);
size_t encSetRoom(uint8_t newVer, const SetRoom&, uint8_t* out, size_t cap);
bool decSetRoom(const uint8_t* p, uint8_t n, uint8_t& newVer, SetRoom&);
size_t encAck(const Ack&, uint8_t* out, size_t cap);
bool decAck(const uint8_t* p, uint8_t n, Ack&);
size_t encStatus(const Status&, uint8_t* out, size_t cap);
bool decStatus(const uint8_t* p, uint8_t n, Status&);
size_t encHello(const Hello&, uint8_t* out, size_t cap);
bool decHello(const uint8_t* p, uint8_t n, Hello&);

// FILE 본문(레코드 스트림) 순회 — 노드가 /schedule.bin 등을 읽을 때 사용.
// pos 는 0 에서 시작해 호출마다 전진. 끝이면 false. 형식 오류면 false + pos 를 n 으로 설정.
bool nextRecord(const uint8_t* body, uint16_t n, uint16_t& pos, uint8_t& recType, const uint8_t*& rec, uint8_t& recLen);
// 레코드 본문(NEW_VER 없음) 디코더 — SLOT_SET/RESV_SET/EXAM_SET 페이로드의 NEW_VER 뒤와 같은 형식
bool decSlotBody(const uint8_t* p, uint8_t n, SlotRec&);
bool decResvBody(const uint8_t* p, uint8_t n, ResvRec&);
bool decExamBody(const uint8_t* p, uint8_t n, ExamRec&);
size_t encSlotBody(const SlotRec&, uint8_t* out, size_t cap);
size_t encResvBody(const ResvRec&, uint8_t* out, size_t cap);
size_t encExamBody(const ExamRec&, uint8_t* out, size_t cap);
```

`lora_codec.cpp`의 `matchesAck` 아래, `}  // namespace lc` 앞에 추가:
```cpp
// ---------- 바이트 커서 ----------
namespace {

struct W {
  uint8_t* o; size_t cap, i = 0; bool ok = true;
  W(uint8_t* out, size_t c) : o(out), cap(c) {}
  void u8(unsigned v, unsigned lo = 0, unsigned hi = 255) {
    if (v < lo || v > hi || i >= cap) { ok = false; return; }
    o[i++] = (uint8_t)v;
  }
  void u16(unsigned v) { u8(v >> 8); u8(v & 0xFF); }
  void u32(uint32_t v) { u16(v >> 16); u16(v & 0xFFFF); }
  void raw(const uint8_t* p, size_t n) { if (i + n > cap) { ok = false; return; } for (size_t k = 0; k < n; ++k) o[i++] = p[k]; }
  void str(const char* s, size_t maxLen) {
    size_t n = 0; while (s[n] && n <= maxLen) ++n;
    if (n > maxLen) { ok = false; return; }
    u8((unsigned)n); raw((const uint8_t*)s, n);
  }
  size_t done() const { return ok ? i : 0; }
};

struct R {
  const uint8_t* p; size_t n, i = 0; bool ok = true;
  R(const uint8_t* b, size_t len) : p(b), n(len) {}
  uint8_t u8(unsigned lo = 0, unsigned hi = 255) {
    if (i >= n) { ok = false; return 0; }
    uint8_t v = p[i++]; if (v < lo || v > hi) ok = false; return v;
  }
  uint16_t u16() { uint16_t a = u8(); return (uint16_t)((a << 8) | u8()); }
  uint32_t u32() { uint32_t a = u16(); return (a << 16) | u16(); }
  const uint8_t* raw(size_t k) { if (i + k > n) { ok = false; return nullptr; } const uint8_t* q = p + i; i += k; return q; }
  void str(char* dst, size_t maxLen) {
    uint8_t len = u8(); if (!ok || len > maxLen) { ok = false; dst[0] = 0; return; }
    const uint8_t* s = raw(len); if (!ok) { dst[0] = 0; return; }
    for (uint8_t k = 0; k < len; ++k) dst[k] = (char)s[k]; dst[len] = 0;
  }
  bool done() const { return ok && i == n; }
};

void hm(W& w, uint8_t h, uint8_t m) { w.u8(h, 0, 23); w.u8(m, 0, 59); }

}  // namespace

// ---------- 본문(NEW_VER 없음) — FILE 레코드와 공유 ----------
size_t encSlotBody(const SlotRec& s, uint8_t* out, size_t cap) {
  W w(out, cap); w.u8(s.day, 1, 7); hm(w, s.sH, s.sM); hm(w, s.eH, s.eM); w.u8(s.type, 1, 6);
  w.str(s.subj, LP_SUBJ_MAX); w.str(s.prof, LP_PROF_MAX); return w.done();
}
bool decSlotBody(const uint8_t* p, uint8_t n, SlotRec& s) {
  R r(p, n); s.day = r.u8(1, 7); s.sH = r.u8(0, 23); s.sM = r.u8(0, 59); s.eH = r.u8(0, 23); s.eM = r.u8(0, 59);
  s.type = r.u8(1, 6); r.str(s.subj, LP_SUBJ_MAX); r.str(s.prof, LP_PROF_MAX); return r.done();
}
size_t encResvBody(const ResvRec& x, uint8_t* out, size_t cap) {
  W w(out, cap); w.u16(x.resvId); w.u8(x.y); w.u8(x.m, 1, 12); w.u8(x.d, 1, 31); hm(w, x.sH, x.sM); hm(w, x.eH, x.eM);
  w.u8(x.type, 1, 6); w.str(x.subj, LP_SUBJ_MAX); w.str(x.prof, LP_PROF_MAX); return w.done();
}
bool decResvBody(const uint8_t* p, uint8_t n, ResvRec& x) {
  R r(p, n); x.resvId = r.u16(); x.y = r.u8(); x.m = r.u8(1, 12); x.d = r.u8(1, 31); x.sH = r.u8(0, 23); x.sM = r.u8(0, 59);
  x.eH = r.u8(0, 23); x.eM = r.u8(0, 59); x.type = r.u8(1, 6); r.str(x.subj, LP_SUBJ_MAX); r.str(x.prof, LP_PROF_MAX);
  return r.done();
}
size_t encExamBody(const ExamRec& e, uint8_t* out, size_t cap) {
  W w(out, cap); w.u16(e.examId); w.u8(e.y1); w.u8(e.m1, 1, 12); w.u8(e.d1, 1, 31); w.u8(e.y2); w.u8(e.m2, 1, 12);
  w.u8(e.d2, 1, 31); return w.done();
}
bool decExamBody(const uint8_t* p, uint8_t n, ExamRec& e) {
  R r(p, n); e.examId = r.u16(); e.y1 = r.u8(); e.m1 = r.u8(1, 12); e.d1 = r.u8(1, 31); e.y2 = r.u8(); e.m2 = r.u8(1, 12);
  e.d2 = r.u8(1, 31); return r.done();
}

// NEW_VER + 본문 조합 헬퍼
#define LC_ENC_VER(NAME, T, BODY)                                                       \
  size_t enc##NAME(uint8_t newVer, const T& x, uint8_t* out, size_t cap) {             \
    if (cap < 1) return 0;                                                              \
    out[0] = newVer; size_t n = BODY(x, out + 1, cap - 1); return n ? n + 1 : 0;        \
  }
#define LC_DEC_VER(NAME, T, BODY)                                                       \
  bool dec##NAME(const uint8_t* p, uint8_t n, uint8_t& newVer, T& x) {                  \
    if (n < 1) return false; newVer = p[0]; return BODY(p + 1, (uint8_t)(n - 1), x);    \
  }
LC_ENC_VER(SlotSet, SlotRec, encSlotBody)  LC_DEC_VER(SlotSet, SlotRec, decSlotBody)
LC_ENC_VER(ResvSet, ResvRec, encResvBody)  LC_DEC_VER(ResvSet, ResvRec, decResvBody)
LC_ENC_VER(ExamSet, ExamRec, encExamBody)  LC_DEC_VER(ExamSet, ExamRec, decExamBody)

// ---------- 단순 타입 ----------
size_t encTime(const Time& t, uint8_t* out, size_t cap) { W w(out, cap); w.u32(t.epoch); w.u8(t.flags); return w.done(); }
bool decTime(const uint8_t* p, uint8_t n, Time& t) { R r(p, n); t.epoch = r.u32(); t.flags = r.u8(); return r.done(); }

size_t encSlotDel(uint8_t nv, const SlotDel& s, uint8_t* out, size_t cap) { W w(out, cap); w.u8(nv); w.u8(s.day, 1, 7); hm(w, s.sH, s.sM); return w.done(); }
bool decSlotDel(const uint8_t* p, uint8_t n, uint8_t& nv, SlotDel& s) { R r(p, n); nv = r.u8(); s.day = r.u8(1, 7); s.sH = r.u8(0, 23); s.sM = r.u8(0, 59); return r.done(); }

size_t encDayClear(uint8_t nv, const DayClear& d, uint8_t* out, size_t cap) { W w(out, cap); w.u8(nv); w.u8(d.day, 1, 7); return w.done(); }
bool decDayClear(const uint8_t* p, uint8_t n, uint8_t& nv, DayClear& d) { R r(p, n); nv = r.u8(); d.day = r.u8(1, 7); return r.done(); }

size_t encResvDel(uint8_t nv, const ResvDel& x, uint8_t* out, size_t cap) { W w(out, cap); w.u8(nv); w.u16(x.resvId); return w.done(); }
bool decResvDel(const uint8_t* p, uint8_t n, uint8_t& nv, ResvDel& x) { R r(p, n); nv = r.u8(); x.resvId = r.u16(); return r.done(); }

size_t encExamDel(uint8_t nv, const ExamDel& x, uint8_t* out, size_t cap) { W w(out, cap); w.u8(nv); w.u16(x.examId); return w.done(); }
bool decExamDel(const uint8_t* p, uint8_t n, uint8_t& nv, ExamDel& x) { R r(p, n); nv = r.u8(); x.examId = r.u16(); return r.done(); }

size_t encFileBegin(uint8_t nv, const FileBegin& f, uint8_t* out, size_t cap) { W w(out, cap); w.u8(nv); w.u8(f.kind, 1, 3); w.u16(f.totalLen); w.u8(f.nChunks); return w.done(); }
bool decFileBegin(const uint8_t* p, uint8_t n, uint8_t& nv, FileBegin& f) { R r(p, n); nv = r.u8(); f.kind = r.u8(1, 3); f.totalLen = r.u16(); f.nChunks = r.u8(); return r.done(); }

size_t encFileData(const FileData& f, uint8_t* out, size_t cap) { if (f.len > LP_FILE_CHUNK_MAX) return 0; W w(out, cap); w.u8(f.seq); w.raw(f.data, f.len); return w.done(); }
bool decFileData(const uint8_t* p, uint8_t n, FileData& f) { if (n < 1 || n - 1 > LP_FILE_CHUNK_MAX) return false; f.seq = p[0]; f.data = p + 1; f.len = (uint8_t)(n - 1); return true; }

size_t encFileEnd(const FileEnd& f, uint8_t* out, size_t cap) { W w(out, cap); w.u16(f.crc); return w.done(); }
bool decFileEnd(const uint8_t* p, uint8_t n, FileEnd& f) { R r(p, n); f.crc = r.u16(); return r.done(); }

size_t encCmd(const CmdMsg& c, uint8_t* out, size_t cap) { W w(out, cap); w.u8(c.cmd, LP_CMD_TEST_RENDER, LP_CMD_FORCE_RENDER); w.raw(c.args, c.argsLen); return w.done(); }
bool decCmd(const uint8_t* p, uint8_t n, CmdMsg& c) { if (n < 1 || p[0] < LP_CMD_TEST_RENDER || p[0] > LP_CMD_FORCE_RENDER) return false; c.cmd = p[0]; c.args = p + 1; c.argsLen = (uint8_t)(n - 1); return true; }

size_t encSetRoom(uint8_t nv, const SetRoom& s, uint8_t* out, size_t cap) { W w(out, cap); w.u8(nv); w.raw(s.mac, 6); w.u8(s.bld); w.u16(s.room); w.u8(s.unit, 0, 2); return w.done(); }
bool decSetRoom(const uint8_t* p, uint8_t n, uint8_t& nv, SetRoom& s) {
  R r(p, n); nv = r.u8(); const uint8_t* m = r.raw(6); if (!r.ok) return false;
  for (int k = 0; k < 6; ++k) s.mac[k] = m[k];
  s.bld = r.u8(); s.room = r.u16(); s.unit = r.u8(0, 2); return r.done();
}

static void ackW(W& w, const Ack& a) { w.u8(a.status, 0, 8); w.u8(a.detail); w.u16(a.battMv); w.u8(a.schedVer); w.u8(a.resvVer); w.u8(a.examVer); w.u8(a.identVer); w.u8(a.fw); w.u8(a.layout, 0, 8); }
static void ackR(R& r, Ack& a) { a.status = r.u8(0, 8); a.detail = r.u8(); a.battMv = r.u16(); a.schedVer = r.u8(); a.resvVer = r.u8(); a.examVer = r.u8(); a.identVer = r.u8(); a.fw = r.u8(); a.layout = r.u8(0, 8); }

size_t encAck(const Ack& a, uint8_t* out, size_t cap) { W w(out, cap); ackW(w, a); return w.done(); }
bool decAck(const uint8_t* p, uint8_t n, Ack& a) { R r(p, n); ackR(r, a); return r.done(); }

size_t encStatus(const Status& s, uint8_t* out, size_t cap) { W w(out, cap); ackW(w, s.ack); w.u8((uint8_t)s.rssiLast); w.u8((uint8_t)s.snrLastX4); w.u8(s.flags); w.u16(s.uptimeH); return w.done(); }
bool decStatus(const uint8_t* p, uint8_t n, Status& s) { R r(p, n); ackR(r, s.ack); s.rssiLast = (int8_t)r.u8(); s.snrLastX4 = (int8_t)r.u8(); s.flags = r.u8(); s.uptimeH = r.u16(); return r.done(); }

size_t encHello(const Hello& h, uint8_t* out, size_t cap) { W w(out, cap); w.raw(h.mac, 6); w.u8(h.fw); w.u16(h.battMv); return w.done(); }
bool decHello(const uint8_t* p, uint8_t n, Hello& h) { R r(p, n); const uint8_t* m = r.raw(6); if (!r.ok) return false; for (int k = 0; k < 6; ++k) h.mac[k] = m[k]; h.fw = r.u8(); h.battMv = r.u16(); return r.done(); }

bool nextRecord(const uint8_t* body, uint16_t n, uint16_t& pos, uint8_t& recType, const uint8_t*& rec, uint8_t& recLen) {
  if (pos >= n) return false;
  if (pos + 2 > n) { pos = n; return false; }
  recType = body[pos]; recLen = body[pos + 1];
  if (pos + 2 + recLen > n) { pos = n; return false; }
  rec = body + pos + 2; pos = (uint16_t)(pos + 2 + recLen); return true;
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd firmware && pio test -e native && pio check --fail-on-defect medium --fail-on-defect high && clang-format --dry-run --Werror lib/lora_codec/*.h lib/lora_codec/*.cpp test/test_codec/*.cpp`
Expected: `8 test cases: 8 succeeded`, 결함 0, 포맷 지적 없음. (`clang-format -i`로 정리했으면 다시 `pio test`.)

- [ ] **Step 5: 커밋**

```bash
git add firmware/lib/lora_codec firmware/test/test_codec
git commit -m "feat(firmware): 전 TYPE 페이로드 codec과 test_vectors.json 필드·재인코딩 검증"
```

---

### Task 10: `modempi` 패키지 뼈대 + 라인 전송 인터페이스 + fake 모뎀

**Files:**
- Create: `modempi/pyproject.toml`, `modempi/modempi/__init__.py`, `modempi/modempi/lora/__init__.py`, `modempi/modempi/lora/transport.py`, `modempi/modempi/lora/fake_modem.py`, `modempi/tests/__init__.py`, `modempi/tests/conftest.py`, `modempi/tests/test_fake_modem_basic.py`, `modempi/tests/test_fake_modem_script.py`, `modempi/tests/test_fake_modem_node.py`

**Interfaces:**
- Produces: `transport.LineTransport` (Protocol: `async write_line(str)`, `async read_line() -> str`, `async close()`), `fake_modem.FakeModem(net_id=P.NET_ID, latency_ms=0, fw="gw-2.0.0")` — `LineTransport` 구현. 메서드 `add_node(bld, room, unit, *, sched_ver=0, resv_ver=0, exam_ver=0, ident_ver=1, batt_mv=4000, fw=20, layout=4)`, `script(outcomes: list[str])`, `inject_uplink(frame: bytes, *, rssi=-100, snr=5.0)`, 속성 `log: list[tuple[str, dict]]` (`("host", msg)` / `("modem", msg)`), `nodes: dict[tuple[int,int,int], NodeState]`, `stats: dict`
- S6의 실물 `modem.py`는 `pyserial-asyncio` 위에 같은 `LineTransport`를 구현한다. 워커는 `LineTransport`만 본다.
- 설계 결정: fake는 **시리얼 라인 수준**(v2 §4.2·4.3 JSON 그대로)에서 흉내낸다. 그래야 S6 드라이버·파서까지 fake로 검증된다.
- 스크립트 토큰(한 `tx`당 하나, 앞에서부터 소비, 비면 자동 판정): `auto` · `no_ack` · `cad_busy` · `bad_crc8` · `ack:OK` · `ack:BUSY` · `ack:STORE_FAIL` · `ack:BAD_PAYLOAD` · `ack:UNSUPPORTED`
- 자동 판정 규칙(가상 노드): 대상 (bld,room,unit) 미등록 → `no_ack` (BROADCAST 플래그면 `sent`/`acked` 없이 `sent`) · `ack_ms==0` → `sent` · 같은 TXN 재수신 → `ACK DUP` · 변경 다운링크에서 `(new_ver - 현재 ver) mod 256 != 1` → `ACK GAP` (적용은 함) · FILE_END 시 누락 seq → `ACK FILE_MISSING(detail=첫 누락)` · 그 외 `ACK OK`. 헤더 `unit=0`은 실제 노드가 없으므로 `no_ack` (유닛 분해는 파이프라인 책임)

- [ ] **Step 1: 실패하는 테스트**

`modempi/tests/conftest.py`:
```python
import json

import pytest

from lora_proto import codec as C
from lora_proto import proto as P
from modempi.lora.fake_modem import FakeModem

E = ord("E")


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def frame(type_, payload, *, bld=E, room=301, unit=1, txn=7, flags=P.FLAG_ACK_REQ) -> bytes:
    return C.encode_frame(C.Header(type=type_, bld=bld, room=room, unit=unit, txn=txn, flags=flags), C.encode_payload(payload))


async def send(m: FakeModem, msg: dict) -> dict:
    """한 줄 보내고 다음 응답 한 줄을 받는다."""
    await m.write_line(json.dumps(msg))
    return json.loads(await m.read_line())


@pytest.fixture
async def modem():
    m = FakeModem()
    m.add_node(E, 301, 1, sched_ver=2)
    assert json.loads(await m.read_line())["op"] == "ready"
    yield m
    await m.close()
```

`modempi/tests/test_fake_modem_basic.py`:
```python
import json

import pytest

from lora_proto import codec as C
from lora_proto import proto as P
from modempi.lora.fake_modem import FakeModem

from .conftest import E, frame, hexs, send

pytestmark = pytest.mark.anyio


async def test_ready_line_first():
    m = FakeModem()
    r = json.loads(await m.read_line())
    assert r["op"] == "ready" and r["fw"] == "gw-2.0.0" and r["sf"] == P.RADIO["RP_SF"] and r["freq"] == 922.5


async def test_ping_pong_and_stats(modem):
    assert (await send(modem, {"op": "ping"}))["op"] == "pong"
    s = await send(modem, {"op": "stats"})
    assert s["op"] == "stats" and s["tx"] == 0


async def test_tx_acked_updates_node_and_returns_decodable_ack(modem):
    f = frame(P.Type.SLOT_SET, C.SlotSet(3, 3, 9, 0, 10, 50, 1, "s", "p"))
    r = await send(modem, {"op": "tx", "id": 17, "frame": hexs(f), "wake": True, "ack_ms": 3000})
    assert r["op"] == "tx_done" and r["id"] == 17 and r["status"] == "acked"
    assert isinstance(r["rssi"], int) and isinstance(r["snr"], float) and r["air_ms"] > 0
    h, pb = C.decode_frame(bytes.fromhex(r["ack"].replace(" ", "")))
    req_h, _ = C.decode_frame(f)
    assert req_h.matches_ack(h)
    ack = C.decode_payload(P.Type.ACK, pb)
    assert ack.status == P.AckStatus.OK and ack.sched_ver == 3
    assert modem.nodes[(E, 301, 1)].sched_ver == 3
    assert modem.stats["tx"] == 1 and modem.stats["acked"] == 1


async def test_ack_ms_zero_is_sent(modem):
    f = frame(P.Type.TIME, C.Time(1_757_400_000, 0), bld=P.BLD_ALL, room=P.ROOM_ALL, unit=0, txn=0, flags=P.FLAG_BROADCAST)
    r = await send(modem, {"op": "tx", "id": 1, "frame": hexs(f), "wake": True, "ack_ms": 0})
    assert r["status"] == "sent"


async def test_unregistered_target_no_ack(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0), room=999)
    r = await send(modem, {"op": "tx", "id": 2, "frame": hexs(f), "wake": True, "ack_ms": 500})
    assert r["status"] == "no_ack"


async def test_unit0_is_not_a_node(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0), unit=0)
    r = await send(modem, {"op": "tx", "id": 3, "frame": hexs(f), "wake": True, "ack_ms": 500})
    assert r["status"] == "no_ack"


async def test_bad_frame_is_error(modem):
    f = bytearray(frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0))); f[-1] ^= 0xFF
    r = await send(modem, {"op": "tx", "id": 4, "frame": hexs(bytes(f)), "wake": False, "ack_ms": 100})
    assert r["status"] == "error" and r["reason"] == "bad_crc8"


async def test_unparseable_line_is_logged_and_ignored(modem):
    await modem.write_line("this is not json")
    r = json.loads(await modem.read_line())
    assert r["op"] == "log" and r["level"] == "warn"


async def test_uplink_injection_arrives_as_rx(modem):
    st = C.Status(C.Ack(0, 0, 3900, 2, 0, 0, 1, 20, 4), -90, 20, 0, 10)
    f = frame(P.Type.STATUS, st, txn=0, flags=0)
    modem.inject_uplink(f, rssi=-90, snr=5.0)
    r = json.loads(await modem.read_line())
    assert r["op"] == "rx" and r["rssi"] == -90 and bytes.fromhex(r["frame"].replace(" ", "")) == f
```

`modempi/tests/test_fake_modem_script.py`:
```python
import asyncio
import json

import pytest

from lora_proto import codec as C
from lora_proto import proto as P

from .conftest import frame, hexs, send

pytestmark = pytest.mark.anyio
F = frame(P.Type.DAY_CLEAR, C.DayClear(3, 2))


async def test_script_no_ack_then_auto(modem):
    modem.script(["no_ack"])
    r1 = await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    r2 = await send(modem, {"op": "tx", "id": 2, "frame": hexs(F), "wake": True, "ack_ms": 100})
    assert r1["status"] == "no_ack" and r2["status"] == "acked"


async def test_script_cad_busy_reports_tries(modem):
    modem.script(["cad_busy"])
    r = await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    assert r["status"] == "cad_busy" and r["tries"] == P.RADIO["RP_CAD_MAX_TRIES"]


@pytest.mark.parametrize("tok,status", [("ack:BUSY", P.AckStatus.BUSY), ("ack:STORE_FAIL", P.AckStatus.STORE_FAIL), ("ack:BAD_PAYLOAD", P.AckStatus.BAD_PAYLOAD)])
async def test_script_forced_ack_status(modem, tok, status):
    modem.script([tok])
    r = await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    _, pb = C.decode_frame(bytes.fromhex(r["ack"].replace(" ", "")))
    assert r["status"] == "acked" and C.decode_payload(P.Type.ACK, pb).status == status


async def test_forced_busy_does_not_apply_version(modem):
    modem.script(["ack:BUSY"])
    await send(modem, {"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100})
    assert modem.nodes[(ord("E"), 301, 1)].sched_ver == 2


async def test_concurrent_tx_rejected_with_busy():
    from modempi.lora.fake_modem import FakeModem
    m = FakeModem(latency_ms=200); m.add_node(ord("E"), 301, 1, sched_ver=2)
    await m.read_line()
    await m.write_line(json.dumps({"op": "tx", "id": 1, "frame": hexs(F), "wake": True, "ack_ms": 100}))
    await asyncio.sleep(0.02)
    await m.write_line(json.dumps({"op": "tx", "id": 2, "frame": hexs(F), "wake": True, "ack_ms": 100}))
    first = json.loads(await m.read_line()); second = json.loads(await m.read_line())
    assert first == {"op": "tx_done", "id": 2, "status": "error", "reason": "busy"}
    assert second["id"] == 1 and second["status"] == "acked"
    await m.close()


async def test_unknown_token_raises(modem):
    with pytest.raises(ValueError):
        modem.script(["explode"])
```

`modempi/tests/test_fake_modem_node.py`:
```python
import pytest

from lora_proto import codec as C
from lora_proto import proto as P

from .conftest import E, frame, hexs, send

pytestmark = pytest.mark.anyio


async def tx(modem, f, id_=1):
    r = await send(modem, {"op": "tx", "id": id_, "frame": hexs(f), "wake": True, "ack_ms": 100})
    assert r["status"] == "acked", r
    _, pb = C.decode_frame(bytes.fromhex(r["ack"].replace(" ", "")))
    return C.decode_payload(P.Type.ACK, pb)


async def test_same_txn_is_dup_without_reapply(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0), txn=9)
    a1 = await tx(modem, f); a2 = await tx(modem, f, 2)
    assert a1.status == P.AckStatus.OK and a2.status == P.AckStatus.DUP
    assert modem.nodes[(E, 301, 1)].sched_ver == 3


async def test_version_gap_is_reported_but_applied(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(5, 1, 9, 0), txn=10)   # 현재 2 → 5 (3, 4 유실)
    a = await tx(modem, f)
    assert a.status == P.AckStatus.GAP and a.sched_ver == 5
    assert modem.nodes[(E, 301, 1)].sched_ver == 5


async def test_version_rollover_255_to_1_is_continuous(modem):
    modem.nodes[(E, 301, 1)].sched_ver = 255
    a = await tx(modem, frame(P.Type.SLOT_DEL, C.SlotDel(1, 1, 9, 0), txn=11))
    assert a.status == P.AckStatus.OK and a.sched_ver == 1


async def test_kinds_have_independent_versions(modem):
    a = await tx(modem, frame(P.Type.RESV_DEL, C.ResvDel(1, 5), txn=12))
    assert a.status == P.AckStatus.OK and a.resv_ver == 1 and a.sched_ver == 2
    a = await tx(modem, frame(P.Type.EXAM_DEL, C.ExamDel(1, 5), txn=13))
    assert a.status == P.AckStatus.OK and a.exam_ver == 1


async def test_file_session_complete(modem):
    recs = [C.SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(12)]
    parts = C.build_file(P.FileKind.SCHEDULE, recs, new_ver=3)
    txn = 20
    for p in parts:
        t = C.type_of(p)
        a = await tx(modem, frame(t, p, txn=txn, flags=P.FLAG_ACK_REQ)); txn += 1
    assert a.status == P.AckStatus.OK and a.sched_ver == 3
    assert len(modem.nodes[(E, 301, 1)].files[P.FileKind.SCHEDULE]) == len(recs)


async def test_file_session_missing_chunk(modem):
    recs = [C.SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(12)]
    begin, d0, d1, d2, end = C.build_file(P.FileKind.SCHEDULE, recs, new_ver=3)
    txn = 30
    for p in (begin, d0, d2):   # d1 누락
        await tx(modem, frame(C.type_of(p), p, txn=txn)); txn += 1
    a = await tx(modem, frame(P.Type.FILE_END, end, txn=txn))
    assert a.status == P.AckStatus.FILE_MISSING and a.detail == 1
    assert modem.nodes[(E, 301, 1)].sched_ver == 2   # 미적용
    # 누락분 재송 후 END 재시도 → OK
    await tx(modem, frame(P.Type.FILE_DATA, d1, txn=txn + 1))
    a = await tx(modem, frame(P.Type.FILE_END, end, txn=txn + 2))
    assert a.status == P.AckStatus.OK and a.sched_ver == 3


async def test_set_room_provisions_unprovisioned_node(modem):
    mac = bytes.fromhex("a0b1c2d3e4f5")
    modem.add_unprovisioned(mac)
    f = frame(P.Type.SET_ROOM, C.SetRoom(1, mac, E, 302, 1), bld=P.BLD_UNPROVISIONED, room=0, unit=0, txn=1)
    a = await tx(modem, f)
    assert a.status == P.AckStatus.OK and (E, 302, 1) in modem.nodes and modem.nodes[(E, 302, 1)].ident_ver == 1


async def test_cmd_request_status_emits_rx(modem):
    await tx(modem, frame(P.Type.CMD, C.Cmd(P.Cmd.REQUEST_STATUS), txn=40))
    import json
    r = json.loads(await modem.read_line())
    assert r["op"] == "rx"
    h, pb = C.decode_frame(bytes.fromhex(r["frame"].replace(" ", "")))
    assert h.type == P.Type.STATUS and C.decode_payload(P.Type.STATUS, pb).ack.sched_ver == 2
```

- [ ] **Step 2: 실패 확인**

`modempi/pyproject.toml`:
```toml
[project]
name = "modempi"
version = "0.1.0"
description = "모뎀Pi 서비스 — WS 링크(wj) + LoRa 파이프라인(cw)"
requires-python = ">=3.12"
dependencies = [
  "lora-proto",
]

[tool.uv.sources]
lora-proto = { path = "../lora_proto", editable = true }

[dependency-groups]
dev = ["pytest>=8.3", "anyio>=4.6", "ruff>=0.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["modempi"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
testpaths = ["tests"]
```
`modempi/modempi/__init__.py`, `modempi/modempi/lora/__init__.py`, `modempi/tests/__init__.py`: 빈 파일.

Run: `cd modempi && uv sync && uv run pytest -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'modempi.lora.fake_modem'`

- [ ] **Step 3: 구현**

`modempi/modempi/lora/transport.py`:
```python
"""모뎀과의 라인 전송 계약. 실물(modem.py, S6)은 pyserial-asyncio 위에, fake 는 메모리 큐 위에 구현한다."""

from __future__ import annotations

from typing import Protocol


class LineTransport(Protocol):
    async def write_line(self, line: str) -> None:
        """'\\n' 없는 한 줄(JSON)을 모뎀에 쓴다."""

    async def read_line(self) -> str:
        """모뎀이 올린 다음 한 줄을 돌려준다. 없으면 기다린다."""

    async def close(self) -> None: ...
```

`modempi/modempi/lora/fake_modem.py`:
```python
"""v2 §4.2·4.3 모뎀 시리얼 프로토콜을 그대로 말하는 가짜 모뎀 + 가상 ESP노드.

워커·드라이버를 하드웨어 없이 검증하기 위한 것. 재시도·TXN 배정은 여기 없다(파이프라인 책임).
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass, field

from lora_proto import codec as C
from lora_proto import proto as P

_TOKENS = {"auto", "no_ack", "cad_busy", "bad_crc8"} | {f"ack:{s.name}" for s in P.AckStatus}
_KIND_OF_TYPE = {
    P.Type.SLOT_SET: P.FileKind.SCHEDULE, P.Type.SLOT_DEL: P.FileKind.SCHEDULE, P.Type.DAY_CLEAR: P.FileKind.SCHEDULE,
    P.Type.RESV_SET: P.FileKind.RESV, P.Type.RESV_DEL: P.FileKind.RESV,
    P.Type.EXAM_SET: P.FileKind.EXAM, P.Type.EXAM_DEL: P.FileKind.EXAM,
}


@dataclass
class NodeState:
    bld: int
    room: int
    unit: int
    sched_ver: int = 0
    resv_ver: int = 0
    exam_ver: int = 0
    ident_ver: int = 1
    batt_mv: int = 4000
    fw: int = 20
    layout: int = P.Layout.EMPTY
    last_txn: int | None = None
    files: dict[int, list] = field(default_factory=dict)          # kind → 마지막 FILE 로 받은 레코드
    _file: dict | None = None                                     # 진행 중 FILE 세션

    def ver(self, kind: int) -> int:
        return {P.FileKind.SCHEDULE: self.sched_ver, P.FileKind.RESV: self.resv_ver, P.FileKind.EXAM: self.exam_ver}[kind]

    def set_ver(self, kind: int, v: int) -> None:
        if kind == P.FileKind.SCHEDULE: self.sched_ver = v
        elif kind == P.FileKind.RESV: self.resv_ver = v
        else: self.exam_ver = v

    def ack(self, status: int, detail: int = 0) -> C.Ack:
        return C.Ack(status, detail, self.batt_mv, self.sched_ver, self.resv_ver, self.exam_ver, self.ident_ver, self.fw, self.layout)

    def status(self) -> C.Status:
        return C.Status(self.ack(P.AckStatus.OK), -95, 24, 0, 100)


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def _air_ms(frame_len: int, wake: bool) -> int:
    # SF9/BW125 대략치: 심볼 4.096 ms, 페이로드 ~ 8 심볼/16 B + 헤더. wake 프리앰블은 RP_PREAMBLE_WAKE_MS.
    return int((P.RADIO["RP_PREAMBLE_WAKE_MS"] if wake else 8 * 4.096) + 60 + frame_len * 5.5)


class FakeModem:
    """LineTransport 구현. 생성 직후 `ready` 한 줄이 큐에 들어 있다."""

    def __init__(self, *, net_id: int = P.NET_ID, latency_ms: int = 0, fw: str = "gw-2.0.0"):
        self.net_id, self.latency_ms, self.fw = net_id, latency_ms, fw
        self.nodes: dict[tuple[int, int, int], NodeState] = {}
        self.unprovisioned: dict[bytes, NodeState] = {}
        self.log: list[tuple[str, dict]] = []
        self.stats = {"tx": 0, "acked": 0, "no_ack": 0, "cad_busy": 0, "rx": 0}
        self._script: list[str] = []
        self._out: asyncio.Queue[str] = asyncio.Queue()
        self._inflight: asyncio.Task | None = None
        self._rng = random.Random(1)
        self._emit({"op": "ready", "fw": fw, "sf": P.RADIO["RP_SF"], "freq": P.RADIO["RP_FREQ_MHZ"]})

    # ----- 테스트 제어 -----
    def add_node(self, bld: int, room: int, unit: int, **kw) -> NodeState:
        n = NodeState(bld, room, unit, **kw); self.nodes[(bld, room, unit)] = n; return n

    def add_unprovisioned(self, mac: bytes, **kw) -> NodeState:
        n = NodeState(P.BLD_UNPROVISIONED, 0, 0, ident_ver=0, **kw); self.unprovisioned[bytes(mac)] = n; return n

    def script(self, outcomes: list[str]) -> None:
        bad = [t for t in outcomes if t not in _TOKENS]
        if bad:
            raise ValueError(f"알 수 없는 스크립트 토큰 {bad}; 허용: {sorted(_TOKENS)}")
        self._script.extend(outcomes)

    def inject_uplink(self, frame: bytes, *, rssi: int = -100, snr: float = 5.0) -> None:
        self.stats["rx"] += 1
        self._emit({"op": "rx", "rssi": rssi, "snr": snr, "frame": _hex(frame)})

    # ----- LineTransport -----
    async def write_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
            op = msg["op"]
        except (ValueError, KeyError, TypeError):
            self._emit({"op": "log", "level": "warn", "msg": f"parse error: {line[:60]!r}"}); return
        self.log.append(("host", msg))
        if op == "ping":
            self._emit({"op": "pong", "uptime_s": 12345})
        elif op == "stats":
            self._emit({"op": "stats", **self.stats})
        elif op == "reset":
            self._emit({"op": "ready", "fw": self.fw, "sf": P.RADIO["RP_SF"], "freq": P.RADIO["RP_FREQ_MHZ"]})
        elif op == "cfg":
            pass  # §4.2: 응답 없음. 기록만.
        elif op == "tx":
            if self._inflight and not self._inflight.done():
                self._emit({"op": "tx_done", "id": msg.get("id"), "status": "error", "reason": "busy"}); return
            self._inflight = asyncio.create_task(self._do_tx(msg))
        else:
            self._emit({"op": "log", "level": "warn", "msg": f"unknown op {op!r}"})

    async def read_line(self) -> str:
        return await self._out.get()

    async def close(self) -> None:
        if self._inflight and not self._inflight.done():
            self._inflight.cancel()

    # ----- 내부 -----
    def _emit(self, msg: dict) -> None:
        self.log.append(("modem", msg)); self._out.put_nowait(json.dumps(msg))

    def _next_token(self) -> str:
        return self._script.pop(0) if self._script else "auto"

    async def _do_tx(self, msg: dict) -> None:
        id_ = msg.get("id"); wake = bool(msg.get("wake")); ack_ms = int(msg.get("ack_ms", 0))
        self.stats["tx"] += 1
        raw = bytes.fromhex(str(msg.get("frame", "")).replace(" ", ""))
        try:
            h, pb = C.decode_frame(raw, net_id=self.net_id)
        except C.FrameError:
            self._emit({"op": "tx_done", "id": id_, "status": "error", "reason": "bad_crc8"}); return
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        tok = self._next_token()
        if tok == "bad_crc8":
            self._emit({"op": "tx_done", "id": id_, "status": "error", "reason": "bad_crc8"}); return
        if tok == "cad_busy":
            self.stats["cad_busy"] += 1
            self._emit({"op": "tx_done", "id": id_, "status": "cad_busy", "tries": P.RADIO["RP_CAD_MAX_TRIES"]}); return
        if ack_ms == 0:
            self._emit({"op": "tx_done", "id": id_, "status": "sent"}); return
        node = self._target(h, pb)
        if tok == "no_ack" or node is None:
            self.stats["no_ack"] += 1
            self._emit({"op": "tx_done", "id": id_, "status": "no_ack"}); return
        forced = P.AckStatus[tok[4:]] if tok.startswith("ack:") else None
        ack = node.ack(forced) if forced is not None else self._apply(node, h, pb)
        ack_frame = C.encode_frame(C.Header(P.Type.ACK, h.bld, h.room, h.unit, h.txn), C.encode_payload(ack))
        self.stats["acked"] += 1
        self._emit({"op": "tx_done", "id": id_, "status": "acked", "rssi": -90 - self._rng.randint(0, 15),
                    "snr": round(self._rng.uniform(2.0, 9.0), 1), "ack": _hex(ack_frame), "air_ms": _air_ms(len(raw), wake)})
        if h.type == P.Type.CMD and C.decode_payload(h.type, pb).cmd == P.Cmd.REQUEST_STATUS:
            st = C.encode_frame(C.Header(P.Type.STATUS, node.bld, node.room, node.unit, 0), C.encode_payload(node.status()))
            self.inject_uplink(st)

    def _target(self, h: C.Header, pb: bytes) -> NodeState | None:
        if h.type == P.Type.SET_ROOM and h.bld == P.BLD_UNPROVISIONED:
            return self.unprovisioned.get(bytes(C.decode_payload(h.type, pb).mac))
        return self.nodes.get((h.bld, h.room, h.unit))

    def _apply(self, node: NodeState, h: C.Header, pb: bytes) -> C.Ack:
        """v2 §3.5 멱등·§3.4 상태 규칙대로 가상 노드에 적용하고 ACK 를 만든다."""
        if node.last_txn == h.txn:
            return node.ack(P.AckStatus.DUP)
        node.last_txn = h.txn
        try:
            p = C.decode_payload(h.type, pb)
        except C.FrameError:
            return node.ack(P.AckStatus.BAD_PAYLOAD)
        t = h.type
        if t in _KIND_OF_TYPE:
            kind = _KIND_OF_TYPE[t]; gap = (p.new_ver - node.ver(kind)) % 256 != 1
            node.set_ver(kind, p.new_ver)
            return node.ack(P.AckStatus.GAP if gap else P.AckStatus.OK)
        if t == P.Type.FILE_BEGIN:
            node._file = {"kind": p.kind, "new_ver": p.new_ver, "n": p.n_chunks, "total": p.total_len, "chunks": {}}
            return node.ack(P.AckStatus.OK)
        if t == P.Type.FILE_DATA:
            if node._file is None:
                return node.ack(P.AckStatus.BAD_PAYLOAD)
            node._file["chunks"][p.seq] = p.data
            return node.ack(P.AckStatus.OK)
        if t == P.Type.FILE_END:
            f = node._file
            if f is None:
                return node.ack(P.AckStatus.BAD_PAYLOAD)
            missing = [s for s in range(f["n"]) if s not in f["chunks"]]
            if missing:
                return node.ack(P.AckStatus.FILE_MISSING, missing[0])
            body = b"".join(f["chunks"][s] for s in range(f["n"]))
            if len(body) != f["total"] or C.crc16_ccitt(body) != p.crc16:
                return node.ack(P.AckStatus.BAD_CRC)
            node.files[f["kind"]] = C.decode_records(f["kind"], body)
            gap = (f["new_ver"] - node.ver(f["kind"])) % 256 != 1
            node.set_ver(f["kind"], f["new_ver"]); node._file = None
            return node.ack(P.AckStatus.GAP if gap else P.AckStatus.OK)
        if t == P.Type.SET_ROOM:
            node.bld, node.room, node.unit, node.ident_ver = p.bld, p.room, p.unit, p.new_ver
            self.nodes[(p.bld, p.room, p.unit)] = node
            for mac, n in list(self.unprovisioned.items()):
                if n is node:
                    del self.unprovisioned[mac]
            return node.ack(P.AckStatus.OK)
        if t == P.Type.CMD:
            if p.cmd == P.Cmd.TEST_RENDER and p.args:
                node.layout = p.args[0]
            return node.ack(P.AckStatus.OK)
        return node.ack(P.AckStatus.UNSUPPORTED)
```

- [ ] **Step 4: 통과 확인**

Run: `cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 모두 PASS (basic 9, script 7, node 8), ruff clean. `anyio` 픽스처가 trio 백엔드까지 돌리면 `tests/conftest.py`에 다음을 추가한다:
```python
@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 5: 커밋**

```bash
git add modempi/pyproject.toml modempi/uv.lock modempi/modempi modempi/tests
git commit -m "feat(modempi): 라인 전송 계약과 v2 §4 시리얼 프로토콜 fake 모뎀 (가상 노드·시나리오 스크립트)"
```

---

### Task 11: CI `proto` job + 전체 게이트 + 문서

**Files:**
- Modify: `.github/workflows/ci.yml`, `README.md`, `lora_proto/README.md`(신규), `CLAUDE.md`

**Interfaces:**
- Produces: CI job `proto` (lora_proto 의 pytest + `check_mirror`). 영역 job 은 여전히 4개(`firmware`·`server`·`modempi`·`web`); `proto`는 계약 게이트다.

- [ ] **Step 1: CI에 `proto` job 추가**

`.github/workflows/ci.yml` — `changes.outputs`에 `proto: ${{ steps.filter.outputs.proto }}`, 필터에:
```yaml
            proto:
              - 'lora_proto/**'
              - '.github/workflows/ci.yml'
```
`firmware` job 앞에 삽입:
```yaml
  # ===== proto: 프로토콜 계약 (Python 미러·codec·벡터 드리프트) =====
  proto:
    needs: changes
    if: ${{ needs.changes.outputs.proto == 'true' }}
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: lora_proto
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: setup
        run: |
          pip install uv
          uv sync --frozen
      - name: lint
        run: uv run ruff check . && uv run ruff format --check .
      - name: header ↔ python mirror
        run: uv run python -m tools.check_mirror
      - name: test (벡터 드리프트 포함)
        run: uv run pytest -q
```
주석 두 번째 문단을 갱신: `# 계약(lora_proto/)이 바뀌면 proto·firmware·server·modempi 네 job이 함께 돈다.`

- [ ] **Step 2: 로컬 YAML 검증**

Run: `python -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml',encoding='utf-8')); print(list(d['jobs']))"`
Expected: `['changes', 'proto', 'firmware', 'server', 'modempi', 'web']`

- [ ] **Step 3: 문서**

`lora_proto/README.md`:
```markdown
# lora_proto — 공중 프로토콜 v2 단일 진실원

| 파일 | 역할 |
|---|---|
| `proto.h`, `radio_params.h` | **상수 원본** (C). 펌웨어가 include |
| `lora_proto/proto.py` | Python 미러. `tools/check_mirror.py`가 원본과 diff (CI) |
| `lora_proto/codec.py` | 프레임·페이로드 encode/decode, `build_file` |
| `tools/gen_vectors.py` → `test_vectors.json` | Python 이 만든 27개 프레임. `firmware/test/test_codec`(Unity)이 바이트 단위로 재검증 |

## 상수·규격을 바꿀 때 (lockstep)
1. `proto.h` / `radio_params.h` 수정 → `proto.py` 같은 값으로
2. `uv run python -m tools.check_mirror` → OK
3. `uv run python -m tools.gen_vectors` → `test_vectors.json` 갱신
4. `uv run pytest` 와 `cd ../firmware && pio test -e native` 둘 다 녹색
5. 이 다섯을 **한 PR** 로 먼저 머지한 뒤, 그 규격을 쓰는 펌웨어·modempi 코드 PR

## 개발
    uv sync && uv run pytest -q
```

`README.md`의 문서 목록 아래에 추가:
```markdown
## 구현 상태
- S1 `lora_proto` + codec(C++/Python) + 테스트 벡터 + fake 모뎀 — 완료 (`docs/plans/2026-09-09-s1-lora-proto-codec.md`)
```

루트 `CLAUDE.md` 폴더 구조 요약의 `lora_proto/` 줄을 다음으로:
```
├── lora_proto/   ← 프로토콜 계약: C 헤더 원본 + Python 미러·codec + test_vectors.json (Owner 전담, README 의 lockstep 절차)
```

- [ ] **Step 4: 전체 게이트**

Run (리포 루트에서):
```bash
(cd lora_proto && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run python -m tools.check_mirror) \
&& (cd modempi && uv run pytest -q && uv run ruff check . && uv run ruff format --check .) \
&& (cd firmware && pio test -e native && pio check --fail-on-defect medium --fail-on-defect high) \
&& clang-format --dry-run --Werror firmware/lib/lora_codec/*.h firmware/lib/lora_codec/*.cpp firmware/test/test_codec/*.cpp \
&& pre-commit run --all-files
```
Expected: 전부 PASS·clean. (`pre-commit`이 처음이면 `pip install pre-commit && pre-commit install` 먼저.)

- [ ] **Step 5: 커밋 + PR**

```bash
git add .github/workflows/ci.yml README.md lora_proto/README.md CLAUDE.md
git commit -m "chore(infra): CI proto job, lora_proto README(lockstep 절차), 구현 상태"
git push -u origin cw
gh pr create --base main --head cw --title "feat(proto): S1 — lora_proto·codec(C++/Python)·테스트 벡터·fake 모뎀" --body-file .github/pull_request_template.md
```
PR 본문의 "어떻게 검증했는지"에 Step 4 명령과 결과(테스트 수: lora_proto 42, modempi 24, firmware 8)를 적고, **머지는 팀장**이 한다. CI 6개 job(`changes`·`proto`·`firmware`·`server`·`modempi`·`web`) 녹색 확인.

---

## Self-Review (계획 검토)

**스펙 커버리지**
- v2 §2 무선 파라미터 → Task 1(`RADIO`)·Task 2(`radio_params.h` + 미러 검사) ✅
- v2 §3.1 헤더·CRC8 → Task 3(Python)·Task 8(C++) ✅
- v2 §3.2 TYPE 16종 → Task 1 상수, Task 7 "전 TYPE 벡터 1개 이상" 테스트가 강제 ✅
- v2 §3.3 페이로드 전부 → Task 4·5·6(Python), Task 9(C++). FILE 레코드 순회(`nextRecord`)는 S8 노드가 씀 ✅
- v2 §3.4 ACK status → Task 1 상수, Task 10 fake 가 GAP/DUP/FILE_MISSING/BAD_CRC/BAD_PAYLOAD/UNSUPPORTED 생성 ✅. `STORE_FAIL`·`BUSY`는 스크립트로 강제 ✅
- v2 §3.5 TXN 멱등(DUP) → Task 10 ✅. TXN **배정**은 S6 범위(비범위 명시) ✅
- v2 §4.2·4.3 시리얼 메시지 전부(`tx/cfg/ping/stats/reset`, `ready/tx_done ×4/rx/pong/stats/log`) → Task 10 ✅. §4.4 "한 번에 하나의 tx" busy 규칙 ✅
- v2 §9 레포 구조(`lora_proto/` 4파일, `firmware/lib/lora_codec`, `test/`) → 파일 구조 ✅. 스펙의 `test_vectors.json` 위치 그대로
- v2 §10.1 "Python 벡터 → C++ 검증, 역방향 동일" → Task 7(Python 라운드트립)·Task 9(C++ 디코드 + 재인코딩 = 역방향) ✅
- 로드맵 §4 계약 ①② → Task 2·7·8·10 ✅. §6.1 fake 모뎀 기능표(정상·시나리오 주입·가상 노드 버전·hex 로그) → Task 10 `script/add_node/log` ✅
- 로드맵 §5 S1 완료 기준 "CI 통과" → Task 11 `proto` job ✅

**Placeholder 스캔**: "TBD/TODO/나중에/적절히" 없음. 모든 코드 스텝에 코드 있음. "Task N과 동일" 없음 ✅

**타입 일관성**: Python `SlotSet(new_ver, day, s_h, s_m, e_h, e_m, type, subject, professor)` 필드명이 Task 4·6·7·10 에서 동일. `to_json`이 필드명을 그대로 JSON 키로 쓰고, C++ 테스트(Task 9)가 같은 키(`s_h`, `resv_id`, `batt_mv`…)로 읽음 ✅. C++ `enc*/dec*` 시그니처가 헤더 선언(Task 9 Step 3)과 테스트 호출(Task 9 Step 1)에서 일치 ✅. fake 모뎀이 쓰는 `C.type_of`는 Task 4에서 정의 ✅. `NodeState.files`는 Task 10 테스트 `test_file_session_complete`가 읽음 ✅

**발견해 고친 것**: Task 9 `test_string_over_limit_rejected` 초안이 구조체 버퍼 밖(`subj[21]`)에 쓰고 있었음 → 디코더 한계 검사 + 인코더 범위 검사로 교체.

**가정**: PlatformIO native 빌드에 호스트 C++ 툴체인(gcc/clang)이 필요하다. Windows 개발 PC라면 MSYS2 또는 VS Build Tools를 설치하고 `pio test -e native`가 뜨는지 Task 8 Step 2 에서 먼저 확인한다. CI(ubuntu)는 기본 제공.
