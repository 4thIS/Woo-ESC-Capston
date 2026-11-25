import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

from assistant_proto import (
    FIRST_PREFIX,
    INTENTS,
    canonical_json,
    json_schema,
    parse_form,
    resolve_time,
    resolve_weekdays,
    resolve_when,
)

VEC = Path(__file__).resolve().parents[1] / "vectors" / "forms.v1.jsonl"
ROWS = [json.loads(x) for x in VEC.read_text(encoding="utf-8").splitlines() if x.strip()]
SCHEMA = jsonschema.Draft202012Validator(json_schema())


def test_ids_unique_and_every_intent_has_four():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids))
    c = Counter(r["form"]["intent"] for r in ROWS)
    short = {i: c[i] for i in INTENTS if c[i] < 4}
    assert not short, short


@pytest.mark.parametrize("r", ROWS, ids=lambda r: r["id"])
def test_vector_valid_and_canonical(r):
    assert list(r) == ["id", "prefix", "utterance", "form"]
    assert not list(SCHEMA.iter_errors(r["form"]))
    f = parse_form(r["form"])
    # 파일의 키 순서도 정규형이다 — 학습 정답을 이 파일에서 그대로 뽑아도 같다
    assert canonical_json(f) == json.dumps(r["form"], ensure_ascii=False, separators=(",", ":"))
    assert r["prefix"].endswith(FIRST_PREFIX)


@pytest.mark.parametrize("r", ROWS, ids=lambda r: r["id"])
def test_values_copied_verbatim(r):
    """규칙 1 — type 말고는 문장(접두어 말고 관리자 문장)에 글자 그대로 있어야 한다."""
    for sec in ("target", "set"):
        for k, v in r["form"][sec].items():
            if k == "type":
                continue
            for x in v if k == "rooms" else [v]:
                assert x in r["utterance"], (r["id"], k, x)


def test_fill_always_has_context():
    for r in ROWS:
        if r["form"]["intent"] == "fill":
            assert r["prefix"] != FIRST_PREFIX and r["prefix"].startswith("상태: "), r["id"]


def test_fill_3_uses_preview_question():
    from assistant_proto import rules

    fill3 = next(r for r in ROWS if r["id"] == "fill-3")
    assert fill3["prefix"].split("\n")[1] == f"질문: {rules.PREVIEW_QUESTION}"


NOW = datetime(2026, 11, 25, 10, 0, tzinfo=timezone(timedelta(hours=9)))


def _group(r):
    intent = r["form"]["intent"]
    if intent == "fill":
        intent = r["prefix"].removeprefix("상태: ").split(" ")[0]
    return intent.split(".")[0]


@pytest.mark.parametrize("r", ROWS, ids=lambda r: r["id"])
def test_when_and_time_spans_resolve(r):
    if r["form"]["intent"] in ("cancel", "unknown"):
        return
    grp = _group(r)
    for sec in ("target", "set"):
        d = r["form"][sec]
        if "when" in d:
            got = resolve_weekdays(d["when"]) if grp == "class" else resolve_when(d["when"], NOW)
            assert got is not None, (r["id"], "when", d["when"])
        if "time" in d:
            assert resolve_time(d["time"]) is not None, (r["id"], "time", d["time"])
