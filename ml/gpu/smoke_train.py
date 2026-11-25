"""로컬 GPU 학습 확인 — Gemma 4 E2B LoRA 가 이 PC 메모리에 들어가는지, 실제로 배우는지 본다.

데이터는 0단계 가상 문장 20개(ml/spike/spike_examples.jsonl)를 반복 학습한다(과적합 확인용 — 정확도 판정 아님).
assistant_proto 가 아직 없어 정답 직렬화·지시문은 0단계 하네스와 같은 것을 쓴다.

    ml/out/train-venv/Scripts/python -X utf8 ml/gpu/smoke_train.py --model ml/out/gemma-4-E2B-it --steps 60
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

HERE = Path(__file__).parent
SPIKE = HERE.parent / "spike"
TOP = ["v", "intent", "target", "set"]
FIELDS = ["rooms", "when", "time", "type", "subject", "professor", "reason", "requester"]
# 글자 모델의 선형층만 (이미지·음성 탑은 학습하지 않는다)
TARGET = r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)"


def canonical(form: dict) -> str:
    """0단계 하네스 common.js 의 canonical 과 같은 키 순서·공백 없는 JSON (부록 §1.3 임시판)."""

    def fx(o: dict | None) -> dict:
        return {k: o[k] for k in FIELDS if o and k in o}

    out = {k: fx(form.get(k)) if k in ("target", "set") else form.get(k) for k in TOP}
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def to_prompt_completion(tok, system: str, user: str, answer: str) -> dict:
    """계획서 Task 9 의 to_prompt_completion 과 같은 방식 — 정답 부분에만 손실."""
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": answer},
    ]
    full = tok.apply_chat_template(msgs, tokenize=False, enable_thinking=False)
    prompt = tok.apply_chat_template(
        msgs[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    if not full.startswith(prompt):
        raise ValueError("chat template: 생성 프롬프트가 전체 대화의 앞부분이 아니다")
    completion = full[len(prompt) :]
    # 토크나이저가 BOS 를 스스로 붙일 때만 지운다. Gemma 4 는 add_bos_token=False 라 지우면
    # 학습은 BOS 없이, 생성(chat template)은 BOS 와 함께 돌아 입력이 한 토큰 어긋난다(계획서 Task 9 의 버그).
    adds_bos = tok.bos_token_id is not None and tok("x")["input_ids"][:1] == [tok.bos_token_id]
    if adds_bos and prompt.startswith(tok.bos_token):
        prompt = prompt[len(tok.bos_token) :]
    return {"prompt": prompt, "completion": completion}


def exact_count(model, tok, system: str, examples: list[dict]) -> tuple[int, list[str], float]:
    import torch

    model.eval()
    outs, hits, t0 = [], 0, time.perf_counter()
    for ex in examples:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": ex["user"]}]
        ids = tok.apply_chat_template(
            msgs,
            add_generation_prompt=True,
            enable_thinking=False,
            return_tensors="pt",
            return_dict=True,
        ).to(model.device)
        with torch.no_grad():
            gen = model.generate(**ids, max_new_tokens=256, do_sample=False)
        text = tok.decode(gen[0, ids["input_ids"].shape[1] :], skip_special_tokens=True).strip()
        outs.append(text)
        try:
            hits += canonical(json.loads(text)) == canonical(ex["gold"])
        except (json.JSONDecodeError, AttributeError):
            pass
    return hits, outs, (time.perf_counter() - t0) / len(examples)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--out", type=Path, default=HERE.parent / "out" / "smoke")
    a = ap.parse_args(argv)

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    system = (SPIKE / "system_draft.txt").read_text(encoding="utf-8").strip()
    examples = [
        json.loads(x)
        for x in (SPIKE / "spike_examples.jsonl").read_text(encoding="utf-8").splitlines()
        if x
    ]
    tok = AutoTokenizer.from_pretrained(a.model)
    rows = [to_prompt_completion(tok, system, ex["user"], canonical(ex["gold"])) for ex in examples]

    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16, device_map="cuda")
    # 이미지·음성 탑은 글자 학습에 쓰지 않는다 — GPU 메모리에서 뺀다
    for name in ("audio_tower", "vision_tower", "embed_audio", "embed_vision"):
        if hasattr(model.model, name):
            setattr(model.model, name, None)
    torch.cuda.empty_cache()
    load_s = time.perf_counter() - t0
    weights_gib = torch.cuda.memory_allocated() / 2**30

    before, _, gen_s_before = exact_count(model, tok, system, examples)

    cfg = SFTConfig(
        output_dir=str(a.out),
        max_steps=a.steps,
        learning_rate=a.lr,
        per_device_train_batch_size=a.batch,
        gradient_accumulation_steps=1,
        gradient_checkpointing=True,
        max_length=a.max_len,
        completion_only_loss=True,
        bf16=True,
        logging_steps=10,
        save_strategy="no",
        report_to="none",
        seed=7,
    )
    peft_cfg = LoraConfig(
        r=a.rank,
        lora_alpha=2 * a.rank,
        lora_dropout=0.05,
        target_modules=TARGET,
        task_type="CAUSAL_LM",
    )
    trainer = SFTTrainer(
        model=model,
        args=cfg,
        train_dataset=Dataset.from_list(rows),
        processing_class=tok,
        peft_config=peft_cfg,
    )
    torch.cuda.reset_peak_memory_stats()
    t1 = time.perf_counter()
    trainer.train()
    train_s = time.perf_counter() - t1
    peak_gib = torch.cuda.max_memory_allocated() / 2**30
    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h]

    trainer.save_model(str(a.out / "adapter"))
    after, outs, gen_s_after = exact_count(trainer.model, tok, system, examples)
    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)

    report = {
        "gpu": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "load_s": round(load_s, 1),
        "weights_gib_text_only": round(weights_gib, 2),
        "trainable_params_m": round(trainable / 1e6, 1),
        "steps": a.steps,
        "batch": a.batch,
        "sec_per_step": round(train_s / a.steps, 2),
        "peak_train_gib": round(peak_gib, 2),
        "loss_first": losses[0] if losses else None,
        "loss_last": losses[-1] if losses else None,
        "exact_before": f"{before}/{len(examples)}",
        "exact_after": f"{after}/{len(examples)}",
        "gen_s_per_sentence_before": round(gen_s_before, 2),
        "gen_s_per_sentence_after": round(gen_s_after, 2),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "smoke.json").write_text(
        json.dumps({**report, "outputs_after": outs}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
