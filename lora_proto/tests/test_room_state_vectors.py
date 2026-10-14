"""room_state_vectors.json — 강의실 상태 판정 벡터 (v2 §5.3·§5.4, 이슈 #74).

서버 `room_state`(wj)와 노드 `determineLayout`·`nextChangeAt`(dh-08)이 같은 파일로 대조한다.
여기의 `_ref` 는 규칙을 그대로 옮긴 참조 구현이다 — 벡터가 규칙과 어긋나지 않는지만 본다(배포 코드 아님).
"""

import json
from itertools import pairwise
from pathlib import Path

from lora_proto import proto as P

VEC = Path(__file__).resolve().parents[1] / "room_state_vectors.json"
DATA = json.loads(VEC.read_text(encoding="utf-8"))

TYPE_TO_LAYOUT = {1: 1, 2: 5, 3: 3, 4: 4, 5: 6, 6: 7}  # v2 §5.3 typeToLayout


def _state(slots, resvs, in_exam, t):
    """(layout, 결정한 것) — 결정한 것이 바뀌면 화면(과목 등)이 바뀐다."""
    for i, r in enumerate(resvs):  # 1. 예약
        if r["s"] <= t < r["e"]:
            return TYPE_TO_LAYOUT[r["type"]], ("resv", i)
    for i, s in enumerate(slots):
        if s["s"] <= t < s["e"]:
            if in_exam:  # 2. 시험기간 + 슬롯 안
                return P.Layout.EXAM, ("exam", i)
            return TYPE_TO_LAYOUT[s["type"]], ("slot", i)  # 3. 슬롯 안
    ordered = sorted(slots, key=lambda s: s["s"])
    for a, b in pairwise(ordered):  # 3. 같은 날 수업 슬롯 사이 틈 ≤ 15분 → 쉬는시간
        gap = b["s"] - a["e"]
        both_class = a["type"] == b["type"] == P.SlotType.CLASS
        if both_class and 0 < gap <= P.BREAK_GAP_MAX_MIN and a["e"] <= t < b["s"]:
            return P.Layout.BREAK, ("break", a["e"])
    return P.Layout.EMPTY, ("free", None)


def _ref(slots, resvs, in_exam, at):
    now = _state(slots, resvs, in_exam, at)
    bounds = sorted({x for it in slots + resvs for x in (it["s"], it["e"]) if x > at})
    for b in bounds:
        if _state(slots, resvs, in_exam, b) != now:
            return int(now[0]), b
    return int(now[0]), None  # 자정까지 그대로


def test_break_gap_constant():
    assert P.BREAK_GAP_MAX_MIN == 15


def test_vectors_follow_rule():
    for v in DATA["vectors"]:
        got = _ref(DATA["slots"], v["resvs"], v["in_exam"], v["at"])
        assert got == (v["layout"], v["until"]), v["name"]


def test_vectors_cover_rule_edges():
    names = {v["name"] for v in DATA["vectors"]}
    for must in (
        "break-gap-15-is-break",
        "gap-16-is-free",
        "night-break-5min",
        "back-to-back-class",
    ):
        assert any(must in n for n in names), must
    layouts = {v["layout"] for v in DATA["vectors"]}
    assert {1, 2, 3, 4, 5, 6, 7} <= layouts  # 설정 대기(8)는 정체성 문제라 여기 없음


def test_vector_shape():
    for s in DATA["slots"]:
        assert 0 <= s["s"] < s["e"] <= 24 * 60 and s["type"] in TYPE_TO_LAYOUT
    for v in DATA["vectors"]:
        assert set(v) >= {"name", "resvs", "in_exam", "at", "layout", "until"}, v["name"]
        assert 0 <= v["at"] < 24 * 60
