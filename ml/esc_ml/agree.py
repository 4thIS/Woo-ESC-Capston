"""두 예측 묶음 일치 비교 — 양자화 전(HF 병합 모델)·후(브라우저 배포 모델)가 같은 양식을 내는가."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assistant_proto import FormError, canonical_json, form_to_dict, parse_form

from esc_ml.records import Prediction, read_predictions


def _norm(p: Prediction | None) -> str | None:
    if p is None:
        return None
    try:
        return canonical_json(form_to_dict(parse_form(p.text.strip())))
    except (FormError, ValueError):
        return None


def agreement(
    a: dict[str, Prediction], b: dict[str, Prediction], ids: list[str]
) -> tuple[int, int, list[str]]:
    """(같은 수, 전체, 다른 id). 둘 다 형식 오류여도 '다름'으로 센다."""
    diffs = []
    for i in ids:
        x, y = _norm(a.get(i)), _norm(b.get(i))
        if x is None or x != y:
            diffs.append(i)
    return len(ids) - len(diffs), len(ids), diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.agree", description="예측 일치 비교")
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument(
        "--suite", type=Path, required=True, help="비교할 문장 id 를 이 묶음에서 읽는다"
    )
    a = ap.parse_args(argv)
    ids = [e["id"] for e in json.loads(a.suite.read_text(encoding="utf-8"))["examples"]]
    same, total, diffs = agreement(read_predictions(a.a), read_predictions(a.b), ids)
    print(f"일치 {same}/{total}")
    for d in diffs:
        print(" 다름:", d)
    return 0 if same == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
