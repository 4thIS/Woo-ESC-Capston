"""합격선 (spec §8.3) — 배포할 양자화 모델 기준."""

INTENT_MIN = 0.97
FIELD_MIN = 0.95
EXACT_MIN = 0.90
FORMAT_MAX_GRAMMAR = 0.0  # 문법 강제 도구
FORMAT_MAX_FREE = 0.01  # 문법 강제가 없는 도구
DANGER_MAX = 0.005
LATENCY_MAX_MS = 5000  # 학과 관리자 PC, 문장 1개 평균
