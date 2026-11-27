"""사람 시험 문장 라벨링 — 수집 CSV → test_human.jsonl.

두 모드가 같은 검사(`build_example`)를 쓴다.
- 대화식(기본): 문장마다 intent 와 칸을 입력받아 규격 검사.
- `--labeled`: CSV 에 intent·target·set 열이 이미 있다. 한 줄이라도 검사에 실패하면 아무것도 쓰지 않고
  `id: 사유` 를 모아 출력한 뒤 종료 코드 1.

입력 모양: 'rooms=803, 801; when=이번 주 금요일; type=특강' (rooms 만 쉼표로 여러 개)
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from assistant_proto import (
    FIELD_ORDER,
    FIRST_PREFIX,
    SCHEMA_VERSION,
    FormError,
    canonical_json,
    parse_form,
    render_prefix,
)

from esc_ml.records import Example, missing_spans, read_examples, write_examples


def parse_kv(line: str) -> dict:
    out: dict = {}
    for part in line.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"'칸=값' 모양이 아님: {part}")
        k, v = (s.strip() for s in part.split("=", 1))
        if k not in FIELD_ORDER:
            raise ValueError(f"모르는 칸: {k}")
        out[k] = [x.strip() for x in v.split(",") if x.strip()] if k == "rooms" else v
    return out


def parse_items(text: str) -> list[tuple[str, str | None]]:
    items = []
    for part in text.split(";"):
        part = part.strip()
        if part:
            if "=" not in part:
                raise ValueError(f"'칸=값' 모양이 아님(ctx_items): {part}")
            k, v = (s.strip() for s in part.split("=", 1))
            items.append((k, None if v == "?" else v))
    return items


def row_prefix(row: dict) -> str:
    if not (row.get("ctx_intent") or "").strip():
        return FIRST_PREFIX
    return render_prefix(
        row["ctx_intent"].strip(),
        parse_items(row.get("ctx_items") or ""),
        (row.get("ctx_question") or "").strip(),
    )


def _now(text: str) -> str:
    try:
        day, hm = text.strip().split()
        h, m = hm.split(":")
        int(h), int(m)
        if len(day.split("-")) != 3:
            raise ValueError
    except ValueError:
        raise ValueError(f"now 는 'YYYY-MM-DD HH:MM' 이어야 함: {text!r}") from None
    return f"{day}T{hm}:00+09:00"


def build_example(row: dict, intent: str, target: dict, set_: dict) -> tuple[Example, list[str]]:
    """두 모드 공통 검사·조립. 규격 위반은 ValueError/FormError, 문장에 없는 값은 두 번째 반환값."""
    if not (row.get("utterance") or "").strip():
        raise ValueError("utterance 가 비었음")
    form = {"v": SCHEMA_VERSION, "intent": intent, "target": target, "set": set_}
    parse_form(form)
    ex = Example(
        id=f"h-{row['id']}",
        split="test",
        template="human",
        now=_now(row["now"]),
        prefix=row_prefix(row),
        utterance=row["utterance"],
        form=form,
    )
    return ex, missing_spans(row["utterance"], form)


def label_row(row: dict, ask, say) -> Example:
    say(f"\n[{row['id']}]\n{row_prefix(row)}{row['utterance']}")
    while True:
        intent = ask("intent> ").strip()
        try:
            target = parse_kv(ask("target> "))
            set_ = parse_kv(ask("set> "))
            ex, miss = build_example(row, intent, target, set_)
        except (ValueError, FormError) as e:
            say(f"다시: {e}")
            continue
        if miss:
            say(f"경고 — 문장에 그대로 없는 값: {miss}")
        say(canonical_json(ex.form))
        if ask("저장? [Y/n]> ").strip().lower() in ("", "y"):
            return ex


def label_given(row: dict) -> Example:
    """라벨이 붙은 줄 → Example. 규격 위반·표현 불일치는 ValueError 로 사유를 돌려준다."""
    ex, miss = build_example(
        row,
        (row.get("intent") or "").strip(),
        parse_kv(row.get("target") or ""),
        parse_kv(row.get("set") or ""),
    )
    if miss:
        raise ValueError(f"문장에 그대로 없는 값: {miss}")
    return ex


def labeled_main(csvs: list[Path], out: Path) -> int:
    exs: list[Example] = []
    errors: list[str] = []
    seen: set[str] = set()
    for path in csvs:
        with path.open(encoding="utf-8-sig", newline="") as f:
            for n, row in enumerate(csv.DictReader(f), start=2):
                row["id"] = (row.get("id") or "").strip()
                rid = row["id"] or f"{path.name}:{n}행"
                try:
                    if not row["id"]:
                        raise ValueError("id 가 비었음")
                    if rid in seen:
                        raise ValueError("id 중복")
                    seen.add(rid)
                    exs.append(label_given(row))
                except (ValueError, FormError) as e:
                    errors.append(f"{rid}: {e}")
    if errors:
        print(f"검사 실패 {len(errors)}줄 (저장하지 않음):")
        print(*errors, sep="\n")
        return 1
    write_examples(out, exs)
    print(f"시험 {len(exs)}문장 → {out}")
    for intent, c in sorted(Counter(e.form["intent"] for e in exs).items()):
        print(f"  {intent}: {c}")
    print(f"이어지는 턴 {sum(e.prefix != FIRST_PREFIX for e in exs)}문장")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.label", description="사람 시험 문장 라벨링")
    ap.add_argument("--csv", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=Path("data/test_human.jsonl"))
    ap.add_argument(
        "--labeled",
        action="store_true",
        help="intent·target·set 열이 이미 있는 CSV 를 한꺼번에 검사·변환",
    )
    a = ap.parse_args(argv)
    if a.labeled:
        return labeled_main(a.csv, a.out)
    if len(a.csv) != 1:
        ap.error("대화식 모드는 --csv 파일 하나만 받는다")
    done = read_examples(a.out) if a.out.exists() else []
    seen = {e.id for e in done}
    with a.csv[0].open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if f"h-{r['id']}" not in seen]
    print(
        f"라벨할 문장 {len(rows)}개 (이미 {len(done)}개). 중간에 Ctrl+C 로 멈춰도 저장된 것까지 남는다."
    )
    for r in rows:
        done.append(label_row(r, input, print))
        write_examples(a.out, done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
