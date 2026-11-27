"""학습 문장 다양화 — 변형 문장 파일을 만들 요청(export)과, 돌려받은 변형을 해석기로 거르는 일(ingest).

변형 문장은 이 프로그램이 만들지 않는다(API 호출 없음). export 가 쓴 요청 파일과 INSTRUCTIONS.md 를
Claude Code 서브에이전트 등이 읽고 `batch-NNNN.out.jsonl` 을 써 두면, ingest 가 해석기로 뜻이 같은
변형만 남긴다. 가상 데이터만 다룬다.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from assistant_proto import FormError, parse_form
from assistant_proto.resolve import normalize_room, resolve_time, resolve_weekdays, resolve_when

from esc_ml.records import SPAN_FIELDS, Example, read_examples, write_examples

REASON_LABELS = {
    "malformed": "변형 모양이 틀림",
    "same_text": "원래 문장과 같음",
    "new_field": "원래 없던 칸이 생김",
    "missing_field": "원래 있던 칸이 빠짐",
    "value_changed": "해석기로 풀어 보니 값이 달라짐",
    "span_not_in_text": "칸 값이 변형 문장 안에 글자 그대로 없음",
    "invalid_form": "양식 검증 실패",
}


def _fields_schema() -> dict:
    nullable_str = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    props = {k: dict(nullable_str) for k in SPAN_FIELDS}
    props["rooms"] = {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(SPAN_FIELDS),
        "properties": props,
    }


def variant_schema() -> dict:
    """출력 한 줄의 JSON Schema — INSTRUCTIONS.md 에 실린다."""
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "target", "set"],
        "properties": {
            "text": {"type": "string"},
            "target": _fields_schema(),
            "set": _fields_schema(),
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "variants"],
        "properties": {"id": {"type": "string"}, "variants": {"type": "array", "items": item}},
    }


def instructions_text() -> str:
    fields = ", ".join(SPAN_FIELDS)
    schema = json.dumps(variant_schema(), ensure_ascii=False, indent=2)
    nulls = ", ".join(f'"{k}": null' for k in SPAN_FIELDS)
    return f"""# 변형 문장 만들기 지시문

너는 대학 강의실 관리자가 AI 비서에게 하는 요청 문장의 변형을 만든다.
모든 문장·이름·강의실·교수·학생은 **가상 데이터**이며 실제 사람·학교와 관계없다.

## 입력

같은 폴더의 `batch-NNNN.jsonl` 한 줄이 문장 하나다.

```json
{{"id": "g7-t000001", "utterance": "803 금요일 15시부터 18시까지 특강 예약해줘",
  "form": {{"v": 1, "intent": "event.add", "target": {{}},
           "set": {{"rooms": ["803"], "when": "금요일", "time": "15시부터 18시까지", "type": "특강"}}}},
  "k": 3}}
```

- `utterance`: 원래 문장. `form`: 그 문장이 뜻하는 정답 양식 (`target`·`set` 의 값은 문장 속 표현 그대로).
- `k`: 그 문장에서 만들 변형의 개수.

## 할 일

원래 문장과 **뜻이 같고 표현만 다른** 변형 문장 `k`개를 만든다.

- 뜻과 값은 그대로 둔다. 강의실·날짜·시각·유형·이름(과목·행사·교수·신청자)·사유를 다른 값으로
  바꾸지 않는다. 원래 없던 정보(교수·사유·시각 등)를 더하지 않고, 있던 정보를 빼지 않는다.
- 같은 뜻의 다른 표현으로 바꾸는 것은 좋다. 예: "3시부터 6시" → "15시~18시", "803" → "803호",
  "다음 주 화요일" → "담주 화요일".
- 실제 관리자가 쓸 법한 다양성을 준다: 구어체, 존댓말/반말, 줄임말(금욜, 낼, 담주), 띄어쓰기 생략,
  어순 바꾸기, 조사 바꾸기·생략, 가벼운 오타(한 문장에 한 개 정도), 끝맺음 바꾸기("해줘", "부탁", "넣어").
- 변형끼리도, 원래 문장과도 서로 달라야 한다.
- 지시문이 아니라 관리자의 요청 문장만 쓴다. 설명·번호·따옴표를 붙이지 않는다.

## 칸 값 (가장 중요)

각 변형에는 그 문장에 **실제로 쓰인 글자 그대로** 칸 값을 적는다.

- 칸: {fields}. (`type` 은 적지 않는다.) 칸은 `target` 과 `set` 두 묶음에 나뉘어 있고, 원래 `form` 에서
  있던 묶음에 그대로 둔다.
- 값은 변형 문장 안에 글자 그대로(띄어쓰기까지) 들어 있어야 한다. 문장에 없는 글자를 적으면 버려진다.
- 문장에서 표현을 바꿨으면 바꾼 표현을 적는다. (문장이 "금욜"이면 `when` 도 "금욜")
- `rooms` 는 문자열 배열, 나머지는 문자열.
- 원래 `form` 에 없던 칸은 `null`. 모든 칸 이름을 항상 적는다.
- 해석기(날짜·시각 규칙)가 변형 값을 풀어 원래 값과 같은지 검사한다. 시각을 "3시"→"15시"처럼
  같은 뜻으로 바꾸는 것은 통과하지만, 다른 시각이면 버려진다.

## 출력

입력 파일 `batch-NNNN.jsonl` 마다 `batch-NNNN.out.jsonl` 을 같은 폴더에 쓴다
(예: `batch-0001.jsonl` → `batch-0001.out.jsonl`). 입력 한 줄마다 출력 한 줄, id 는 같게.
각 줄은 JSON 한 개다(여러 줄로 나누지 않는다).

```json
{{"id": "g7-t000001", "variants": [
  {{"text": "803호 금욜 3시부터 6시 특강 잡아줘",
   "target": {{{nulls}}},
   "set": {{"rooms": ["803호"], "when": "금욜", "time": "3시부터 6시", "subject": null, "professor": null, "reason": null, "requester": null}}}}
]}}
```

줄 전체의 JSON Schema:

```json
{schema}
```
"""


def check(ex: Example, variant: dict) -> str | None:
    """변형을 받을 수 있나 — 받을 수 있으면 None, 거절이면 사유 코드(REASON_LABELS 의 키)."""
    try:
        text = variant["text"].strip()
        if not text:
            return "malformed"
        if text == ex.utterance:
            return "same_text"
        now = datetime.fromisoformat(ex.now)
        intent = ex.form["intent"]
        form = copy.deepcopy(ex.form)
        for side in ("target", "set"):
            orig, got = ex.form[side], variant[side]
            for f in SPAN_FIELDS:
                new = got.get(f)
                if f not in orig:
                    if new:  # 원래 없던 칸이 생겼다
                        return "new_field"
                    continue
                if not new:
                    return "missing_field"
                if f == "rooms":
                    if not isinstance(new, list) or not all(isinstance(x, str) for x in new):
                        return "malformed"
                elif not isinstance(new, str):
                    return "malformed"
                if not same_value(f, orig[f], new, now, intent):
                    return "value_changed"
                if any(v not in text for v in (new if f == "rooms" else [new])):
                    return "span_not_in_text"
                form[side][f] = list(new) if f == "rooms" else new
    except (KeyError, TypeError, AttributeError, ValueError):
        return "malformed"
    try:
        parse_form(form)
    except FormError:
        return "invalid_form"
    return None


def _squash(s: str) -> str:
    return "".join(s.split())


def same_value(field: str, old, new, now: datetime, intent: str) -> bool:
    """두 표현이 같은 값인가 — 채점기(score.py)와 같은 규칙."""
    if field == "rooms":
        return sorted(normalize_room(x) for x in old) == sorted(normalize_room(x) for x in new)
    if field == "when":
        if intent.startswith("class."):
            a, b = resolve_weekdays(old), resolve_weekdays(new)
        else:
            a, b = resolve_when(old, now), resolve_when(new, now)
        return (a == b) if (a is not None or b is not None) else _squash(old) == _squash(new)
    if field == "time":
        a, b = resolve_time(old), resolve_time(new)
        return (a == b) if (a is not None or b is not None) else _squash(old) == _squash(new)
    return _squash(old) == _squash(new)


def accept(ex: Example, variant: dict, idx: int) -> Example | None:
    if check(ex, variant) is not None:
        return None
    form = copy.deepcopy(ex.form)
    for side in ("target", "set"):
        for f in SPAN_FIELDS:
            if f in ex.form[side]:
                new = variant[side][f]
                form[side][f] = list(new) if f == "rooms" else new
    return replace(
        ex,
        id=f"{ex.id}-p{idx}",
        template=f"{ex.template}+p",
        utterance=variant["text"].strip(),
        form=form,
    )


# --- export / ingest -------------------------------------------------------------


def export(inp: Path, out: Path, batch: int, limit: int, variants: int) -> int:
    rows = [r for r in read_examples(inp) if r.split in ("train", "val")]
    if limit:
        rows = rows[:limit]
    out.mkdir(parents=True, exist_ok=True)
    n_files = 0
    for start in range(0, len(rows), batch):
        n_files += 1
        path = out / f"batch-{n_files:04d}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows[start : start + batch]:
                rec = {"id": r.id, "utterance": r.utterance, "form": r.form, "k": variants}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    (out / "INSTRUCTIONS.md").write_text(instructions_text(), encoding="utf-8", newline="\n")
    print(f"문장 {len(rows)}개 → 요청 파일 {n_files}개 + INSTRUCTIONS.md → {out}")
    return 0


@dataclass
class IngestStats:
    asked: int = 0
    kept: int = 0
    broken: int = 0
    unknown: int = 0
    reasons: Counter = field(default_factory=Counter)


def ingest(inp: Path, variants_dir: Path, out: Path) -> IngestStats:
    by_id = {r.id: r for r in read_examples(inp)}
    stats = IngestStats()
    kept: list[Example] = []
    next_idx: Counter = Counter()
    for path in sorted(Path(variants_dir).glob("*.out.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                rid, vs = rec["id"], rec["variants"]
                if not isinstance(vs, list):
                    raise TypeError("variants")
            except (ValueError, KeyError, TypeError):
                stats.broken += 1
                continue
            ex = by_id.get(rid)
            if ex is None:
                stats.unknown += 1
                continue
            for v in vs:
                stats.asked += 1
                idx = next_idx[rid]
                next_idx[rid] += 1
                reason = check(ex, v) if isinstance(v, dict) else "malformed"
                if reason is None:
                    got = accept(ex, v, idx)
                    assert got is not None
                    kept.append(got)
                    stats.kept += 1
                else:
                    stats.reasons[reason] += 1
    write_examples(out, kept)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.paraphrase", description="학습 문장 다양화")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="변형을 만들 요청 파일과 INSTRUCTIONS.md 쓰기")
    e.add_argument("--in", dest="inp", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--batch", type=int, default=100)
    e.add_argument("--limit", type=int, default=0, help="앞에서 N 문장만 (0 = 전부)")
    e.add_argument("--variants", type=int, default=3)
    g = sub.add_parser("ingest", help="돌려받은 *.out.jsonl 을 해석기로 거르기")
    g.add_argument("--in", dest="inp", type=Path, required=True)
    g.add_argument("--variants-dir", type=Path, required=True)
    g.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "export":
        return export(a.inp, a.out, a.batch, a.limit, a.variants)
    stats = ingest(a.inp, a.variants_dir, a.out)
    print(f"변형 {stats.asked}개 중 {stats.kept}개 남김 → {a.out}")
    for code, n in stats.reasons.most_common():
        print(f"  거절 {REASON_LABELS.get(code, code)}: {n}")
    if stats.broken:
        print(f"  깨진 줄 {stats.broken}개 건너뜀")
    if stats.unknown:
        print(f"  모르는 id {stats.unknown}줄 건너뜀")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
