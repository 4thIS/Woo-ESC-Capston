# 로컬 GPU 학습 절차 (wj 데스크톱 — RTX 5070 Ti 16 GB, bf16)

확인 결과: `ml/reports/gpu-local.md` — bf16 LoRA 최대 11.3 GiB, 배치 4 에서 1.36 s/스텝. 4bit 는 쓰지 않는다.
평소 다른 프로그램이 GPU 메모리를 약 3 GB 쓴다 — 학습 중에는 GPU 를 쓰는 프로그램을 닫는다.

1 — 의존성 (CUDA 판 torch)
    cd ml
    uv sync --extra train
    uv pip install --reinstall torch --index-url https://download.pytorch.org/whl/cu130
    uv run --no-sync python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
→ `True NVIDIA GeForce RTX 5070 Ti`. 아래 명령은 모두 `uv run --no-sync`(sync 가 CPU 판 torch 로 되돌리지 않게).

2 — 데이터 (생성은 seed 로 재현, 다양화는 Task 4 의 로컬 data/para/)
    uv run --no-sync python -m esc_ml.gen --n 8000 --seed 7 --out data/gen

3 — 학습 (bf16, --quant 없음)
    uv run --no-sync python -m esc_ml.train --train data/gen/train.jsonl data/para/train.jsonl \
        --val data/gen/val.jsonl data/para/val.jsonl --out runs/run1

4 — 검증 문장으로 바로 예측(배포 전 감 잡기)
    uv run --no-sync python -m esc_ml.predict_hf --adapter runs/run1/adapter --data data/gen/val.jsonl --limit 200 --out runs/run1/preds-val.jsonl
    uv run --no-sync python -m esc_ml.score --data data/gen/val.jsonl --pred runs/run1/preds-val.jsonl --no-grammar --title "run1 검증" --out runs/run1/val.md

`runs/run1/`(adapter/, run_config.json, val.md)은 커밋하지 않는다.

대체 경로(데스크톱을 못 쓸 때): Kaggle(T4×2·P100)·Colab — `HF_TOKEN` 은 Secrets, 다양화는 `HF_OWNER/esc-assistant-data` 에서 받고, bf16 이 없어 학습·예측에 `--quant 4bit`.
