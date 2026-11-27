"""transformers 모델 불러오기 — 학습·예측·병합 공용. torch 는 함수 안에서 import (CI 는 train extra 없이 돈다)."""

from __future__ import annotations

DEFAULT_MODEL = "google/gemma-4-E2B-it"


def _dtype():
    import torch

    if torch.cuda.is_available():
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return torch.float32


def load_tokenizer(model_id: str):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_id)


def load_model(model_id: str, quant: str = "none", adapter: str | None = None):
    import torch
    from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, BitsAndBytesConfig

    dtype = _dtype()
    kw: dict = {"dtype": dtype, "device_map": "auto" if torch.cuda.is_available() else None}
    if quant == "4bit":
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype
        )
    try:
        model = AutoModelForCausalLM.from_pretrained(model_id, **kw)
    except ValueError:  # 멀티모달 체크포인트(Gemma 4 E2B 는 텍스트·이미지·음성)면 이쪽 클래스
        model = AutoModelForImageTextToText.from_pretrained(model_id, **kw)
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return model
