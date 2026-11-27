"""HF transformers 로 예측 — 원본 기준 점수(예문 몇 개)·튜닝 모델·병합 모델 공용. 출력 = Prediction JSONL."""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

from assistant_proto import SYSTEM_PROMPT, canonical_json

from esc_ml.hf import DEFAULT_MODEL, load_model, load_tokenizer
from esc_ml.records import Example, Prediction, load_vectors, read_examples, write_predictions


def build_messages(ex: Example, fewshot: list[Example]) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for s in fewshot:
        msgs += [
            {"role": "user", "content": s.user_text()},
            {"role": "assistant", "content": canonical_json(s.form)},
        ]
    msgs.append({"role": "user", "content": ex.user_text()})
    return msgs


def pick_fewshot(pool: list[Example], k: int, seed: int) -> list[Example]:
    """intent 가 겹치지 않게 k 개 — 학습 데이터(생성)에서만 고른다(시험 문장·계약 예문 금지)."""
    rng = random.Random(seed)
    shuffled = pool[:]
    rng.shuffle(shuffled)
    out, seen = [], set()
    for e in shuffled:
        if e.form["intent"] not in seen:
            out.append(e)
            seen.add(e.form["intent"])
        if len(out) == k:
            break
    return out


def generate(model, tok, msgs: list[dict], max_new_tokens: int = 256) -> str:
    prompt = tok.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    ids = tok(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
    out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False)
    return tok.decode(out[0, ids["input_ids"].shape[1] :], skip_special_tokens=True).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.predict_hf", description="HF 예측")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--adapter")
    ap.add_argument("--quant", default="none", choices=("none", "4bit"))
    ap.add_argument("--data", type=Path, nargs="*", default=[])
    ap.add_argument("--vectors", type=Path)
    ap.add_argument("--fewshot-pool", type=Path)
    ap.add_argument("--k", type=int, default=0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    exs = [e for p in a.data for e in read_examples(p)]
    if a.vectors:
        exs += load_vectors(a.vectors)
    if a.limit:
        exs = exs[: a.limit]
    shots = pick_fewshot(read_examples(a.fewshot_pool), a.k, a.seed) if a.k else []
    tok = load_tokenizer(a.model)
    model = load_model(a.model, a.quant, a.adapter)
    preds = []
    for i, e in enumerate(exs, 1):
        t0 = time.perf_counter()
        text = generate(model, tok, build_messages(e, shots))
        preds.append(
            Prediction(e.id, text, None)
        )  # GPU 시간은 관리자 PC 응답 시간이 아니라 기록하지 않는다
        if i % 20 == 0:
            print(f"{i}/{len(exs)} ({time.perf_counter() - t0:.2f}s/문장)")
    write_predictions(a.out, preds)
    print(f"예측 {len(preds)}개 → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
