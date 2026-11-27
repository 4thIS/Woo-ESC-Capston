"""예문·예측 레코드 — 생성·다양화·사람 시험·계약 예문·예측이 모두 이 모양을 쓴다."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json

# 문장 속 표현을 그대로 옮기는 칸 (type 만 고르는 칸이라 빠진다 — 부록 §1.1)
SPAN_FIELDS = ("rooms", "when", "time", "subject", "professor", "reason", "requester")
DEFAULT_NOW = "2026-11-25T10:00:00+09:00"


@dataclass(frozen=True)
class Example:
    id: str
    split: str  # train | val | test
    template: str  # 생성 틀 id. 사람 문장 "human", 계약 예문 "vector", 다양화는 "<틀>+p"
    now: str  # 기준 시각 ISO 8601 (KST +09:00) — 채점에서 상대 날짜를 풀 때 쓴다
    prefix: str  # FIRST_PREFIX 또는 render_prefix(...) 결과
    utterance: str
    form: dict  # 정답 양식 (없는 칸은 키를 뺀 dict)

    def user_text(self) -> str:
        return self.prefix + self.utterance

    def messages(self) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self.user_text()},
            {"role": "assistant", "content": canonical_json(self.form)},
        ]


@dataclass(frozen=True)
class Prediction:
    id: str
    text: str  # 모델 출력 그대로
    latency_ms: float | None = None


def _lines(path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _write_lines(path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_examples(path) -> list[Example]:
    return [Example(**r) for r in _lines(path)]


def write_examples(path, rows) -> None:
    _write_lines(path, [asdict(r) for r in rows])


def read_predictions(path) -> dict[str, Prediction]:
    out = {}
    for r in _lines(path):
        out[r["id"]] = Prediction(r["id"], r["text"], r.get("latency_ms"))
    return out


def write_predictions(path, preds) -> None:
    _write_lines(path, [asdict(p) for p in preds])


def span_values(form: dict) -> list[str]:
    out: list[str] = []
    for side in ("target", "set"):
        for key in SPAN_FIELDS:
            v = form.get(side, {}).get(key)
            if v is None:
                continue
            out += list(v) if key == "rooms" else [v]
    return out


def missing_spans(utterance: str, form: dict) -> list[str]:
    """정답 표현 중 문장에 글자 그대로 없는 것 — 생성기·다양화·라벨링의 공통 검사."""
    return [v for v in span_values(form) if v not in utterance]


def load_vectors(path) -> list[Example]:
    """계약 예문 → Example. 줄 모양은 Example 키(id·now·prefix·utterance·form)를 따르고, 없는 키는 기본값."""
    rows = []
    for i, r in enumerate(_lines(path)):
        rows.append(
            Example(
                id=f"v-{r.get('id', i)}",
                split="test",
                template="vector",
                now=r.get("now", DEFAULT_NOW),
                prefix=r.get("prefix", FIRST_PREFIX),
                utterance=r["utterance"],
                form=r["form"],
            )
        )
    return rows
