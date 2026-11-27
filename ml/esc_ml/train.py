"""LoRA SFT — 정답(양식 JSON)에만 손실을 거는 prompt-completion 형식. 생각 모드는 끈다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from esc_ml.hf import DEFAULT_MODEL, load_model, load_tokenizer
from esc_ml.records import Example, read_examples

# 글자 모델만 LoRA — all-linear 면 Gemma 4 의 이미지·음성 탑까지 학습한다(#173)
TARGET = r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)"
DROP = ("audio_tower", "vision_tower", "embed_audio", "embed_vision")


def to_prompt_completion(tok, ex: Example) -> dict:
    msgs = ex.messages()
    full = tok.apply_chat_template(msgs, tokenize=False, enable_thinking=False)
    prompt = tok.apply_chat_template(
        msgs[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    if not full.startswith(prompt):
        raise ValueError("chat template: 생성 프롬프트가 전체 대화의 앞부분이 아니다 — 템플릿 확인")
    completion = full[len(prompt) :]
    # 토크나이저가 BOS 를 스스로 붙일 때만 지운다(두 번 들어가지 않게). Gemma 4 는 add_bos_token=False 라
    # 지우면 학습은 BOS 없이, 생성(chat template)은 BOS 와 함께 돌아 입력이 한 토큰 어긋난다(#173).
    bos_id = getattr(tok, "bos_token_id", None)
    adds_bos = bos_id is not None and tok("x")["input_ids"][:1] == [bos_id]
    if adds_bos and prompt.startswith(tok.bos_token):
        prompt = prompt[len(tok.bos_token) :]
    return {"prompt": prompt, "completion": completion}


def longest_tokens(tok, rows) -> int:
    """prompt+completion 의 최대 토큰 수 — max_length 보다 길면 정답이 잘려 학습에서 빠진다."""
    return max(
        len(tok(r["prompt"] + r["completion"], add_special_tokens=False)["input_ids"]) for r in rows
    )


def jsonable(args: dict) -> dict:
    """run_config 의 args — 경로·경로 목록(--train a b)을 글자로."""

    def conv(v):
        if isinstance(v, Path):
            return v.as_posix()
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return {k: conv(v) for k, v in args.items()}


def data_digest(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.train", description="LoRA SFT")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--train", type=Path, nargs="+", required=True)
    ap.add_argument("--val", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--quant",
        default="none",
        choices=("none", "4bit"),
        help="로컬 16 GB 는 none(bf16). 대체 경로 T4·P100 만 4bit",
    )
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    # 시스템 지시문 포함 약 700~850 토큰(#180 지시문 기준) — 512 면 정답이 모두 잘린다
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)

    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from trl import SFTConfig, SFTTrainer

    tok = load_tokenizer(a.model)
    train_rows = [e for p in a.train for e in read_examples(p) if e.split == "train"]
    val_rows = [e for p in a.val for e in read_examples(p) if e.split == "val"]
    train_pc = [to_prompt_completion(tok, e) for e in train_rows]
    val_pc = [to_prompt_completion(tok, e) for e in val_rows]
    longest = longest_tokens(tok, train_pc + val_pc)
    if longest > a.max_len:
        raise SystemExit(f"가장 긴 문장 {longest} 토큰 > --max-len {a.max_len} — 정답이 잘린다")
    print(f"학습 {len(train_pc)} · 검증 {len(val_pc)} · 가장 긴 문장 {longest} 토큰")
    train = Dataset.from_list(train_pc)
    val = Dataset.from_list(val_pc)

    model = load_model(a.model, a.quant)
    inner = getattr(model, "model", model)
    for name in DROP:  # 이미지·음성 탑은 글자 학습에 안 쓴다 — 메모리에서 뺀다(약 0.9 GiB)
        if hasattr(inner, name):
            setattr(inner, name, None)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if a.quant == "4bit":
        model = prepare_model_for_kbit_training(model)
    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    cfg = SFTConfig(
        output_dir=str(a.out),
        num_train_epochs=a.epochs,
        learning_rate=a.lr,
        per_device_train_batch_size=a.batch,
        per_device_eval_batch_size=a.batch,
        gradient_accumulation_steps=a.grad_accum,
        gradient_checkpointing=True,
        max_length=a.max_len,
        completion_only_loss=True,
        bf16=bf16,
        fp16=torch.cuda.is_available() and not bf16,
        logging_steps=20,
        eval_strategy="steps",
        eval_steps=200,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        seed=a.seed,
        report_to="none",
    )
    peft_cfg = LoraConfig(
        r=a.rank,
        lora_alpha=a.alpha,
        lora_dropout=0.05,
        target_modules=TARGET,
        task_type="CAUSAL_LM",
    )
    trainer = SFTTrainer(
        model=model,
        args=cfg,
        train_dataset=train,
        eval_dataset=val,
        processing_class=tok,
        peft_config=peft_cfg,
    )
    trainer.train()
    trainer.save_model(str(a.out / "adapter"))

    import peft
    import transformers
    import trl

    run = {
        "args": jsonable(vars(a)),
        "train_n": len(train_rows),
        "val_n": len(val_rows),
        "train_digest": data_digest(a.train),
        "val_digest": data_digest(a.val),
        "versions": {
            "transformers": transformers.__version__,
            "trl": trl.__version__,
            "peft": peft.__version__,
        },
        "final": {k: v for k, v in trainer.state.log_history[-1].items()},
        "best_eval_loss": trainer.state.best_metric,
    }
    (a.out / "run_config.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(run["final"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
