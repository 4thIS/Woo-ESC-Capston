import json
from datetime import datetime
from pathlib import Path

import pytest

from assistant_proto import normalize_room, resolve_time, resolve_weekdays, resolve_when

VEC = Path(__file__).resolve().parents[1] / "vectors" / "resolve.v1.jsonl"
ROWS = [json.loads(x) for x in VEC.read_text(encoding="utf-8").splitlines() if x.strip()]


def _when_json(w):
    if w is None:
        return None
    if w.kind == "dates":
        return {"kind": "dates", "dates": [d.isoformat() for d in w.dates]}
    if w.kind == "range":
        return {"kind": "range", "start": w.start.isoformat(), "end": w.end.isoformat()}
    return {"kind": "weekdays", "weekdays": list(w.weekdays)}


def _time_json(t):
    if t is None:
        return None
    return {"start": t.start.strftime("%H:%M"), "end": t.end.strftime("%H:%M") if t.end else None}


@pytest.mark.parametrize("v", ROWS, ids=lambda v: f"{v['fn']}:{v['expr']}")
def test_vector(v):
    now = datetime.fromisoformat(v["now"])
    if v["fn"] == "when":
        assert _when_json(resolve_when(v["expr"], now)) == v["expect"]
    elif v["fn"] == "weekdays":
        got = resolve_weekdays(v["expr"])
        assert (list(got) if got else None) == v["expect"]
    elif v["fn"] == "time":
        assert _time_json(resolve_time(v["expr"])) == v["expect"]
    else:
        assert normalize_room(v["expr"]) == v["expect"]


def test_every_function_has_vectors():
    assert {v["fn"] for v in ROWS} == {"when", "weekdays", "time", "room"}


def test_naive_now_works_too():
    # 서버는 KST naive 시각을 넘긴다 — .date() 만 쓰므로 같다
    naive = datetime(2026, 11, 25, 10, 0)  # noqa: DTZ001 — naive 가 이 테스트의 목적
    assert resolve_when("내일", naive).dates[0].isoformat() == "2026-11-26"
