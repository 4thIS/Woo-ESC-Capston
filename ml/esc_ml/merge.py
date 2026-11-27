"""LoRA 병합 — 양자화 없는 원본에 어댑터를 합쳐 safetensors 로 저장(변환 도구의 입력)."""

from __future__ import annotations

import argparse
from pathlib import Path

from esc_ml.hf import DEFAULT_MODEL, load_model, load_tokenizer


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.merge", description="LoRA 병합")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    model = load_model(a.model, "none", a.adapter).merge_and_unload()
    model.save_pretrained(a.out, safe_serialization=True)
    load_tokenizer(a.model).save_pretrained(a.out)
    try:  # 멀티모달 체크포인트의 전처리 설정(변환 도구가 읽는다)
        from transformers import AutoProcessor

        AutoProcessor.from_pretrained(a.model).save_pretrained(a.out)
    except (OSError, ValueError):
        pass
    print(f"병합 → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
