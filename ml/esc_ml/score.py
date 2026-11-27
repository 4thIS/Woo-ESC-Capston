"""채점기 — HF 예측·브라우저 하네스 예측을 같은 규칙으로 채점하고 보고서를 만든다 (spec §8.3)."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from assistant_proto import FormError, canonical_json, form_to_dict, parse_form

from esc_ml import gates as G
from esc_ml.paraphrase import same_value
from esc_ml.records import Example, Prediction, load_vectors, read_examples, read_predictions


@dataclass(frozen=True)
class Row:
    id: str
    intent_gold: str
    intent_pred: str | None
    format_ok: bool
    exact: bool
    fields_ok: int
    fields_total: int
    dangerous: bool
    latency_ms: float | None
    error: str = ""


@dataclass(frozen=True)
class Summary:
    n: int
    intent_acc: float
    field_acc: float
    exact_acc: float
    format_err: float
    danger_rate: float
    latency_mean_ms: float | None
    latency_p90_ms: float | None


@dataclass(frozen=True)
class Gate:
    name: str
    value: str
    threshold: str
    passed: bool | None  # None = 해당 없음


def _items(form: dict) -> dict[tuple[str, str], object]:
    return {(side, k): v for side in ("target", "set") for k, v in form.get(side, {}).items()}


def _is_write(intent: str) -> bool:
    return intent.endswith((".add", ".change")) or intent == "request.approve"


def _is_destructive(intent: str) -> bool:
    return intent.endswith(".remove") or intent == "request.reject"


def score_one(ex: Example, pred: Prediction | None) -> Row:
    gold = _items(ex.form)
    gi = ex.form["intent"]
    lat = pred.latency_ms if pred else None
    if pred is None:
        return Row(ex.id, gi, None, False, False, 0, len(gold), False, None, "예측 없음")
    try:
        pd = form_to_dict(parse_form(pred.text.strip()))
    except (FormError, ValueError) as e:
        return Row(ex.id, gi, None, False, False, 0, len(gold), False, lat, f"형식: {e}")
    now = datetime.fromisoformat(ex.now)
    got = _items(pd)
    keys = set(gold) | set(got)
    ok = sum(
        1 for k in keys if k in gold and k in got and same_value(k[1], gold[k], got[k], now, gi)
    )
    pi = pd["intent"]
    exact = pi == gi and ok == len(keys)
    return Row(
        ex.id, gi, pi, True, exact, ok, len(keys), _is_write(gi) and _is_destructive(pi), lat
    )


def summarize(rows: list[Row]) -> Summary:
    n = len(rows)
    writes = [r for r in rows if _is_write(r.intent_gold)]
    lats = sorted(r.latency_ms for r in rows if r.latency_ms is not None)
    total = sum(r.fields_total for r in rows)
    return Summary(
        n=n,
        intent_acc=sum(r.intent_pred == r.intent_gold for r in rows) / n,
        field_acc=sum(r.fields_ok for r in rows) / total if total else 1.0,
        exact_acc=sum(r.exact for r in rows) / n,
        format_err=sum(not r.format_ok for r in rows) / n,
        danger_rate=sum(r.dangerous for r in writes) / len(writes) if writes else 0.0,
        latency_mean_ms=sum(lats) / len(lats) if lats else None,
        latency_p90_ms=lats[max(0, math.ceil(0.9 * len(lats)) - 1)] if lats else None,
    )


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def gate_results(s: Summary, grammar: bool, require_latency: bool = False) -> list[Gate]:
    fmax = G.FORMAT_MAX_GRAMMAR if grammar else G.FORMAT_MAX_FREE
    out = [
        Gate(
            "intent 정확도",
            _pct(s.intent_acc),
            f"≥ {_pct(G.INTENT_MIN)}",
            s.intent_acc >= G.INTENT_MIN,
        ),
        Gate("칸 정확도", _pct(s.field_acc), f"≥ {_pct(G.FIELD_MIN)}", s.field_acc >= G.FIELD_MIN),
        Gate(
            "양식 전체 일치",
            _pct(s.exact_acc),
            f"≥ {_pct(G.EXACT_MIN)}",
            s.exact_acc >= G.EXACT_MIN,
        ),
        Gate(
            f"형식 오류 ({'문법 강제' if grammar else '강제 없음'})",
            _pct(s.format_err),
            f"≤ {_pct(fmax)}",
            s.format_err <= fmax,
        ),
        Gate(
            "위험 오류",
            _pct(s.danger_rate),
            f"≤ {_pct(G.DANGER_MAX)}",
            s.danger_rate <= G.DANGER_MAX,
        ),
    ]
    if s.latency_mean_ms is None:
        out.append(
            Gate(
                "응답 시간 평균",
                "—",
                f"≤ {G.LATENCY_MAX_MS} ms",
                False if require_latency else None,
            )
        )
    else:
        out.append(
            Gate(
                "응답 시간 평균",
                f"{s.latency_mean_ms:.0f} ms (p90 {s.latency_p90_ms:.0f})",
                f"≤ {G.LATENCY_MAX_MS} ms",
                s.latency_mean_ms <= G.LATENCY_MAX_MS,
            )
        )
    return out


def render_report(
    title: str,
    s: Summary,
    rows: list[Row],
    gates: list[Gate],
    examples: dict[str, Example],
    preds: dict[str, Prediction],
    config: dict | None = None,
) -> str:
    mark = {True: "✅", False: "❌", None: "—"}
    lines = [
        f"# {title}",
        "",
        f"- 문장 수: {s.n}",
        "",
        "## 합격선",
        "",
        "| 지표 | 값 | 합격선 | 판정 |",
        "|---|---|---|---|",
    ]
    lines += [f"| {g.name} | {g.value} | {g.threshold} | {mark[g.passed]} |" for g in gates]
    overall = all(g.passed is not False for g in gates)
    lines += ["", f"**종합: {'합격' if overall else '불합격'}**", ""]
    if config:
        lines += [
            "## 설정",
            "",
            "```json",
            json.dumps(config, ensure_ascii=False, indent=1),
            "```",
            "",
        ]
    per: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        per[r.intent_gold].append(r)
    lines += ["## intent 별", "", "| intent | n | intent 정확도 | 전체 일치 |", "|---|---|---|---|"]
    for intent in sorted(per):
        rs = per[intent]
        ia = sum(r.intent_pred == r.intent_gold for r in rs) / len(rs)
        ea = sum(r.exact for r in rs) / len(rs)
        lines.append(f"| {intent} | {len(rs)} | {_pct(ia)} | {_pct(ea)} |")
    fails = [r for r in rows if not r.exact][:30]
    lines += ["", f"## 틀린 문장 (앞 {len(fails)}개)", ""]
    for r in fails:
        e = examples[r.id]
        p = preds.get(r.id)
        lines += [
            f"- `{r.id}` {r.error}",
            f"  - 입력: `{e.user_text()!r}`",
            f"  - 정답: `{canonical_json(e.form)}`",
            f"  - 출력: `{p.text if p else '(없음)'}`",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.score", description="채점·보고서")
    ap.add_argument("--data", type=Path, nargs="*", default=[])
    ap.add_argument("--vectors", type=Path, help="assistant_proto/vectors/forms.v1.jsonl")
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--grammar", action=argparse.BooleanOptionalAction, required=True)
    ap.add_argument("--require-latency", action="store_true")
    ap.add_argument("--config", type=Path, help="학습 run_config.json — 보고서에 함께 적는다")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--json", type=Path, help="요약 수치를 JSON 으로도 (모델 카드용)")
    a = ap.parse_args(argv)

    exs = [e for p in a.data for e in read_examples(p)]
    if a.vectors:
        exs += load_vectors(a.vectors)
    preds = read_predictions(a.pred)
    rows = [score_one(e, preds.get(e.id)) for e in exs]
    s = summarize(rows)
    gates = gate_results(s, a.grammar, a.require_latency)
    config = json.loads(a.config.read_text(encoding="utf-8")) if a.config else None
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(
        render_report(a.title, s, rows, gates, {e.id: e for e in exs}, preds, config),
        encoding="utf-8",
    )
    if a.json:
        a.json.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=1), encoding="utf-8")
    for g in gates:
        print(f"{g.name:20s} {g.value:>22s}  {g.threshold:>12s}  {g.passed}")
    return 0 if all(g.passed is not False for g in gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
