"""브라우저 하네스 묶음 — {system_prompt, json_schema, gbnf, examples:[{id,user,gold}]} (Task 1 모양)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assistant_proto import SYSTEM_PROMPT, json_schema

from esc_ml.records import Example, load_vectors, read_examples


def build_suite(examples: list[Example], gbnf: str | None = None) -> dict:
    return {
        "system_prompt": SYSTEM_PROMPT,
        "json_schema": json_schema(),
        "gbnf": gbnf,
        "examples": [{"id": e.id, "user": e.user_text(), "gold": e.form} for e in examples],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.suite", description="하네스 묶음 만들기")
    ap.add_argument("--data", type=Path, nargs="*", default=[])
    ap.add_argument("--vectors", type=Path)
    ap.add_argument("--gbnf", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    exs = [e for p in a.data for e in read_examples(p)]
    if a.vectors:
        exs += load_vectors(a.vectors)
    if a.limit:
        exs = exs[: a.limit]
    gbnf = a.gbnf.read_text(encoding="utf-8") if a.gbnf else None
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(
        json.dumps(build_suite(exs, gbnf), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"{a.out} — {len(exs)}문장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
