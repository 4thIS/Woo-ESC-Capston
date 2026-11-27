# 로컬 GPU 학습 확인 — Gemma 4 E2B LoRA (wj 데스크톱)

- 날짜: 2026-11-25 / 측정: wj
- 목적: 02 작업지시서 Task 9 는 Kaggle(T4·P100, 4bit QLoRA)을 전제로 한다. wj 데스크톱 GPU 로 **4bit 없이(bf16)** 학습할 수 있는지, 그리고 실제로 배우는지 미리 본다.
- `assistant_proto`(PR A)가 아직 없어 Task 2~7 은 시작 전이다. 그래서 0단계 가상 문장 20개(`ml/spike/spike_examples.jsonl`)를 반복 학습하는 **과적합 확인**만 했다 — 정확도 판정 아님.
- 스크립트: `ml/gpu/smoke_train.py` (학습 설정은 계획서 Task 9 `train.py` 와 같은 SFTTrainer · prompt-completion · `completion_only_loss`)

## 환경

| 항목 | 값 |
|---|---|
| GPU | NVIDIA GeForce RTX 5070 Ti 16 GB (Blackwell, compute 12.0), 드라이버 595.71 |
| 평소 다른 프로그램이 쓰는 GPU 메모리 | 약 3.2 GB → 학습에 쓸 수 있는 것 약 13 GB |
| 설치 | `uv venv ml/out/train-venv` → `torch` (`--index-url https://download.pytorch.org/whl/cu130`) + `transformers peft trl datasets accelerate` |
| 버전 | torch 2.14.1+cu130 · transformers 5.24.1 · peft 0.22.0 · trl 1.18.2 |
| 모델 | `google/gemma-4-E2B-it` (공개, gated 아님) |

## 결과 (bf16, LoRA r16·α32, 배치 4, 60 스텝 = 12 에폭, gradient checkpointing)

| 항목 | 값 |
|---|---|
| 모델 GPU 메모리 (이미지·음성 탑 뺀 뒤) | 8.62 GiB (전체 그대로면 9.51 GiB) |
| 학습 최대 GPU 메모리 | **11.29 GiB** — 16 GB 안에 들어감 |
| 학습 파라미터 (LoRA) | 24.2 M |
| 스텝당 시간 (배치 4, 문장당 약 400 토큰) | **1.36 s** |
| 손실 | 0.270 → 0.0001 |
| 20문장 정답 일치 | 학습 전 **3/20** → 학습 후 **20/20** |

예상 학습 시간(참고): 문장 16,000개 × 3 에폭 ÷ 배치 4 × 1.36 s ≈ **4.5 시간**. 실제 `SYSTEM_PROMPT` 길이·데이터 수가 정해지면 다시 잰다.

### 학습 설정에서 계획서와 다르게 한 것

| 계획서 Task 9 | 이 확인 | 이유 |
|---|---|---|
| `--quant 4bit` (T4·P100) | bf16 그대로 | 5070 Ti 는 bf16 을 지원하고 메모리가 남는다 — 4bit 는 정확도 손해만 있다 |
| `target_modules="all-linear"` | 글자 모델(`language_model`)의 q/k/v/o/gate/up/down 만 | Gemma 4 원본은 이미지·음성 탑을 포함한 멀티모달 모델이라 all-linear 면 탑까지 학습한다 |
| 모델 전체를 GPU 에 | 이미지·음성 탑을 메모리에서 뺌 | 글자 학습에 안 쓰고 약 0.9 GiB 를 차지한다 |
| (언급 없음) | `gradient_checkpointing=True` | 메모리 여유 확보 |

## 계획서 버그 — Task 9 `to_prompt_completion` 의 BOS 처리

계획서는 "토크나이저가 BOS 를 다시 붙인다"며 프롬프트 앞의 `<bos>` 를 지운다. 그런데 **Gemma 4 토크나이저는 `add_bos_token=False`** 라 BOS 를 붙이지 않는다. 그대로 학습하면:

- 학습: `<|turn>system …` (BOS 없음, 401 토큰)
- 실제 생성(chat template): `<bos><|turn>system …` (402 토큰)

로 입력이 한 토큰 어긋난다. 확인 결과 학습 손실은 0.0001 인데 생성 정답은 **14/20 ~ 16/20** 에 그쳤다(정답을 넣은 순전파에서는 50/50 토큰을 모두 맞힘 — 생성 때 입력만 다름). "토크나이저가 BOS 를 스스로 붙일 때만 지운다"로 고치자 입력이 같아지고(391 = 391) **20/20** 이 됐다.

```python
adds_bos = tok.bos_token_id is not None and tok("x")["input_ids"][:1] == [tok.bos_token_id]
if adds_bos and prompt.startswith(tok.bos_token):
    prompt = prompt[len(tok.bos_token) :]
```

계획서의 `test_prompt_completion_split`(`assert not pc["prompt"].startswith("<bos>")`)도 이 동작을 전제로 하므로 함께 고쳐야 한다 — BOS 를 붙이지 않는 토크나이저용 테스트를 하나 더 둔다.

## 결론

- **Task 9 는 Kaggle 대신 wj 데스크톱 GPU 로 한다.** bf16 LoRA 가 11.3 GiB 로 들어가고, 4bit 가 필요 없다.
- Task 9 구현 때 반영: BOS 처리 수정, 글자 모델만 LoRA, 이미지·음성 탑 제외, gradient checkpointing. `notebooks/kaggle_train.md` 대신 로컬 실행 절차를 쓴다.
