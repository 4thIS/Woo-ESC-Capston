"""시험 문장 ↔ 학습 문장 겹침 검사 — 같거나 거의 같은 문장이 학습에 있으면 시험이 의미 없다."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from esc_ml.records import Example, read_examples

_STRIP = re.compile(r"[\s\W_]+")


def norm(s: str) -> str:
    return _STRIP.sub("", s.lower())


def grams(s: str, n: int = 4) -> set[str]:
    t = norm(s)
    return {t[i : i + n] for i in range(max(1, len(t) - n + 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def near_duplicates(
    tests: list[Example], trains: list[Example], threshold: float = 0.8, min_len: int = 8
) -> list[tuple[str, str, float]]:
    """(시험 id, 학습 id, 유사도). 정규화 길이가 min_len 미만인 짧은 말("취소")은 겹쳐도 어쩔 수 없어 뺀다."""
    exact = {norm(t.utterance): t.id for t in trains}
    train_grams = [(t.id, grams(t.utterance)) for t in trains]
    out = []
    for e in tests:
        n = norm(e.utterance)
        if len(n) < min_len:
            continue
        if n in exact:
            out.append((e.id, exact[n], 1.0))
            continue
        g = grams(e.utterance)
        best = max(
            ((tid, jaccard(g, tg)) for tid, tg in train_grams), key=lambda x: x[1], default=None
        )
        if best and best[1] >= threshold:
            out.append((e.id, best[0], round(best[1], 3)))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m esc_ml.overlap", description="시험 ↔ 학습 겹침 검사"
    )
    ap.add_argument("--test", type=Path, nargs="+", required=True)
    ap.add_argument("--train", type=Path, nargs="+", required=True)
    a = ap.parse_args(argv)
    tests = [e for p in a.test for e in read_examples(p)]
    trains = [e for p in a.train for e in read_examples(p)]
    hits = near_duplicates(tests, trains)
    for h in hits:
        print(*h, sep="\t")
    print(f"겹침 {len(hits)}건 / 시험 {len(tests)}문장")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
