# ml — 관리자 AI 비서 모델 (wj)

문장 → 양식 JSON 으로 옮기는 Gemma 4 E2B 파인튜닝. 규격·프롬프트·해석기는 `../assistant_proto/` 가 원본이다.
작업지시서: `docs/plans/2026-11-25-ai-assistant-02-finetune.md`

| 할 일 | 명령 (ml/ 에서) |
|---|---|
| 설치 (채점·생성만) | `uv sync` |
| 설치 (학습) | `uv sync --extra train` |
| 예문 생성 | `uv run python -m esc_ml.gen --n 8000 --seed 7 --out data/gen` |
| 다양화 요청 파일 만들기 | `uv run python -m esc_ml.paraphrase export --in data/gen/train.jsonl --out data/para/req/train --limit 1000 --variants 3` |
| 다양화 결과 받아 거르기 | `uv run python -m esc_ml.paraphrase ingest --in data/gen/train.jsonl --variants-dir data/para/req/train --out data/para/train.jsonl` |
| 시험 문장 라벨 | `uv run python -m esc_ml.label --csv data/raw/human.csv --out data/test_human.jsonl` |
| 겹침 검사 | `uv run python -m esc_ml.overlap --test data/test_human.jsonl --train data/gen/train.jsonl data/para/train.jsonl` |
| HF 예측 | `uv run --extra train python -m esc_ml.predict_hf …` |
| 채점 | `uv run python -m esc_ml.score …` |
| 하네스 | `python spike/serve.py` → http://localhost:8080 |

데이터 원본·모델·변환 산출물은 커밋하지 않는다(`.gitignore`). 공개는 Hugging Face 에만.
