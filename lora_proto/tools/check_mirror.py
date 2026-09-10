"""proto.h·radio_params.h 를 파싱해 lora_proto/proto.py 와 값이 같은지 검사한다. CI 게이트."""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

from lora_proto import proto as P

ROOT = Path(__file__).resolve().parents[1]
_DEFINE = re.compile(r"^\s*#define\s+(\w+)\s+([0-9A-Fa-fx.]+)f?\b")
_ENUM_ITEM = re.compile(r"(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)")
# LP_/RP_ 로 시작하는 #define 은 모두 프로토콜 상수여야 한다 — _DEFINE 이 못 읽으면(값 형식이 특이하거나
# 주석이 붙는 등) 조용히 빠지지 않도록 별도로 잡아낸다.
_LP_RP_DEFINE = re.compile(r"^\s*#define\s+(LP_|RP_)\w+")

# LP_<GROUP>_<NAME> 의 GROUP → proto.py 의 enum 클래스
_GROUPS = {
    "TYPE": P.Type,
    "ACK": P.AckStatus,
    "CMD": P.Cmd,
    "SLOTTYPE": P.SlotType,
    "FILEKIND": P.FileKind,
    "LAYOUT": P.Layout,
    "STATUSFLAG": P.StatusFlag,
    "TIMEFLAG": P.TimeFlag,
}
# 단순 #define → proto.py 모듈 상수
_SCALARS = {
    "LP_PROTO_VER": "PROTO_VER",
    "LP_FLAG_ACK_REQ": "FLAG_ACK_REQ",
    "LP_FLAG_BROADCAST": "FLAG_BROADCAST",
    "LP_FLAG_WAKE_SENT": "FLAG_WAKE_SENT",
    "LP_HEADER_LEN": "HEADER_LEN",
    "LP_MAX_FRAME": "MAX_FRAME",
    "LP_MAX_PAYLOAD": "MAX_PAYLOAD",
    "LP_FILE_CHUNK_MAX": "FILE_CHUNK_MAX",
    "LP_BLD_UNPROVISIONED": "BLD_UNPROVISIONED",
    "LP_BLD_ALL": "BLD_ALL",
    "LP_ROOM_ALL": "ROOM_ALL",
    "LP_UNIT_ALL": "UNIT_ALL",
    "LP_SUBJ_MAX": "SUBJ_MAX",
    "LP_PROF_MAX": "PROF_MAX",
}


def _num(s: str) -> int | float:
    # Remove C float suffix only for floats (not hex numbers)
    if "." in s and s and s[-1] in "fF":
        s = s[:-1]
    return int(s, 16) if s.lower().startswith("0x") else (float(s) if "." in s else int(s))


def parse_defines(path: Path) -> dict[str, int | float]:
    out: dict[str, int | float] = {}
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = _DEFINE.match(line)
        if m and m.group(1) not in ("LORA_PROTO_PROTO_H", "LORA_PROTO_RADIO_PARAMS_H"):
            out[m.group(1)] = _num(m.group(2))
    for body in re.findall(r"enum\s*\{([^}]*)\}", text, re.DOTALL):
        for name, val in _ENUM_ITEM.findall(body):
            out[name] = _num(val)
    return out


def unparsed(path: Path) -> list[str]:
    """LP_/RP_ #define 인데 parse_defines 의 _DEFINE 패턴에 걸리지 않은 원본 줄 (include guard 제외)."""
    out: list[str] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not _LP_RP_DEFINE.match(line):
            continue
        if _DEFINE.match(line):
            continue
        m = re.match(r"^\s*#define\s+(\w+)", line)
        if m and m.group(1) in ("LORA_PROTO_PROTO_H", "LORA_PROTO_RADIO_PARAMS_H"):
            continue
        out.append(line)
    return out


def diff() -> list[str]:
    problems: list[str] = []
    h = parse_defines(ROOT / "proto.h")
    r = parse_defines(ROOT / "radio_params.h")

    for path in (ROOT / "proto.h", ROOT / "radio_params.h"):
        for line in unparsed(path):
            problems.append(f"{path.name}: 파싱 못한 #define: {line.strip()}")

    for cname, pname in _SCALARS.items():
        if cname not in h:
            problems.append(f"proto.h 에 {cname} 없음")
        elif h[cname] != getattr(P, pname):
            problems.append(f"{cname}={h[cname]} != proto.{pname}={getattr(P, pname)}")

    # Reverse check: proto.py scalars not in _SCALARS
    for name in vars(P):
        if not name.isupper() or name in ("NET_ID", "RADIO"):
            continue
        val = getattr(P, name)
        if inspect.isclass(val) or not isinstance(val, int) or isinstance(val, bool):
            continue
        if name not in _SCALARS.values():
            problems.append(f"proto.py 상수 {name} 가 proto.h 에 없음 (매핑 _SCALARS 추가 필요)")

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
    for group, enum in _GROUPS.items():
        for name in enum.__members__:
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
