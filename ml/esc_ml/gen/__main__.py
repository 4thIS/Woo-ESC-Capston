"""python -m esc_ml.gen --n 8000 --seed 7 --out data/gen"""

from __future__ import annotations

import argparse
from pathlib import Path

from esc_ml.gen.build import generate, intent_counts
from esc_ml.records import write_examples


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.gen", description="학습·검증 예문 생성")
    ap.add_argument("--n", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path("data/gen"))
    a = ap.parse_args(argv)
    rows = generate(a.n, a.seed)
    for split in ("train", "val"):
        part = [r for r in rows if r.split == split]
        write_examples(a.out / f"{split}.jsonl", part)
        print(f"{split}: {len(part)}건 → {a.out / f'{split}.jsonl'}")
    for intent, c in sorted(intent_counts(rows).items()):
        print(f"  {intent:16s} {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
