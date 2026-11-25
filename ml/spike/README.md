---
title: esc-spike
emoji: 🧪
sdk: static
app_file: index.html
custom_headers:
  cross-origin-embedder-policy: credentialless
  cross-origin-opener-policy: same-origin
---

ESC 관리자 AI 비서 — 브라우저 실행 도구 실험 하네스(0단계). 모델은 각 도구의 공개 저장소에서 받는다. 데이터는 가상 문장 20개뿐이다.
로컬: `python ml/spike/serve.py` → http://localhost:8080
