# 0단계 — 브라우저 실행 도구 실험 결과

- 날짜: 2026-11-25 / 측정: wj
- 기계 ①: 학과 관리자 PC — **미측정** (아래 「계획서와 다르게 한 것」)
- 기계 ②: wj 데스크톱 — AMD Ryzen 7 9800X3D(16 스레드) / 64 GB / NVIDIA GeForce RTX 5070 Ti(환경 정보 gpu `nvidia / blackwell`) / Chrome 158(Playwright 자동화), `webgpu: true`, `cross_origin_isolated: true`
- 원본 기록: `ml/reports/spike/wj-pc/` — 도구마다 `run-<도구>-<문법>.json`(요약)·`preds-<도구>-<문법>.jsonl`(Prediction)

## 기계 ① 학과 관리자 PC

미측정. 관리자 PC 를 쓸 수 없어 같은 하네스로 다음에 잰다(측정 방법은 계획서 Step 8 그대로).

## 기계 ② wj 데스크톱

| 항목 | WebLLM | Transformers.js | MediaPipe (LiteRT) | wllama |
|---|---|---|---|---|
| 모델 | `gemma-4-E2B-it-q4f16_1-MLC` (미리 만든 목록) | `onnx-community/gemma-4-E2B-it-ONNX` q4f16 | `litert-community/gemma-4-E2B-it-litert-lm` `gemma-4-E2B-it-web.task` (2.0 GB) | `unsloth/gemma-4-E2B-it-GGUF` `Q4_K_M` (3.1 GB) |
| 불러오기 성공 | O | O | O (모델 주소 고친 뒤) | O |
| 첫 다운로드 (s) | 50.6 | 54.2 | 67.1 | 82.2 |
| 캐시 불러오기 (s) | 4.6 | 3.5 | **75.6 — 캐시 안 됨(매번 다시 받음)** | 미측정 |
| 평균 응답 mean_ms / p90_ms | **1,391 / 1,939** | 1,585 / 2,196 | **319 / 525** | 약 30,950 (3문장 뒤 중단) |
| 초당 토큰 | 24.8 | 21.1 | 98.3 | 약 8.3 (256 토큰 / 31 s) |
| 문법 강제 지원 / 켰을 때 규격 통과 (20) | O / **20/20** | X / — | X / — | O / 0/3 (출력 깨짐) |
| 강제 끔 규격 통과 (20) | 15/20 | 16/20 | 17/20 | 미측정 |
| 20문장 정답 일치 (참고, 원본 모델) | 4 (강제 켬) · 3 (끔) | 2 | 2 | 0 |
| 최대 메모리 (탭 + GPU, MB) | 미측정 | 미측정 | 미측정 | 미측정 |
| 콘솔 오류 | 없음 (경고: Windows 에서 `powerPreference` 무시 — crbug 369219127) | 없음 | 없음 | 없음 |
| 변환 경로 사전 확인 (Step 9) | **통과** — 원본을 직접 변환해 출력 20/20 이 미리 만든 모델과 글자까지 같음 (아래 「Step 9」) | 미실시 (2위 이하) | 미실시 (2위 이하) | — (탈락) |
| 비고 | 문법 강제가 실제로 동작하는 유일한 도구 | 문법 강제 없음 | 가장 빠름. 문법 강제 없음. 대화 틀을 Gemma 4 형식으로 고쳐야 동작 | CPU(WASM) 실행. 문법 켬에서 `{{"{{"…` 반복, 256 토큰까지 감 |

정답 일치가 낮은 것은 파인튜닝 전 원본 모델이라서다(계획서도 0단계 정답 일치는 참고용). 주로 틀린 곳: `target`/`set` 을 바꿔 넣음, 되물음 답(`fill`·`cancel`)을 새 요청으로 봄, 칸 이름을 지어냄.

## Step 9 — WebLLM 변환 경로 (원본 `google/gemma-4-E2B-it`)

| 단계 | 명령 | 결과 |
|---|---|---|
| 설치 | `uv venv ml/out/mlc-venv` → `uv pip install --pre -f https://mlc.ai/wheels mlc-llm-nightly-cpu mlc-ai-nightly-cpu psutil` | `mlc-llm-nightly-cpu 0.26.dev20` · `mlc-ai-nightly-cpu 0.26.dev529` (Windows) |
| 고침 | conda-forge `spirv-tools 2026.4` 의 `SPIRV-Tools.dll` 을 `tvm/lib/` 에 복사 | Windows 휠에 이 DLL 이 빠져 `tvm_compiler.dll` 이 안 올라가고 `RegisterOpAttr` 오류가 난다 |
| 가중치 | `python -m mlc_llm convert_weight ml/out/gemma-4-E2B-it --quantization q4f16_1 --device cpu -o ml/spike/models/esc-webllm-base` | 2분 37초, 최대 RAM 9.5 GB, 결과 2.6 GB |
| 설정 | `python -m mlc_llm gen_config ml/out/gemma-4-E2B-it --quantization q4f16_1 --conv-template gemma4_instruction -o …` 후 `context_window_size` 131072 → 4096 | 계획서의 `gemma_instruction` 대신 Gemma 4 틀 `gemma4_instruction` |
| 모델 라이브러리 | 공개본 `binary-mlc-llm-libs/web-llm-models/v0_2_87/base/gemma-4-E2B-it-q4f16_1_cs512-webgpu.wasm` → `lib.wasm` | 같은 구조·양자화라 **compile·emscripten 이 필요 없다** |
| 실행 | 하네스 모델 칸 `models/esc-webllm-base`, 문법 강제 켬 | 불러오기 5.4 s, 평균 1,660 ms, 규격 20/20, 정답 4 — **출력 20문장이 미리 만든 모델과 모두 같음** |

하네스에서 로컬 변환본을 쓰려고 고친 것: `serve.py` 가 WebLLM 이 붙이는 `resolve/main/` 을 지우고, `adapters/webllm.js` 가 Gemma 4 에 필요한 `model_manifest`·`context_window_size` 를 넘긴다.

- Linux nightly(0.26.dev6)는 `gemma4` 를 모른다(지원은 2026-09-29 #3559). Linux·Kaggle 에서 변환하려면 소스 빌드가 필요하다 — 변환은 Windows(위 절차)에서 한다.
- 파인튜닝 모델도 구조가 같으므로 Task 10 갈래 B 는 위 명령에서 입력만 `ml/out/merged` 로 바꾸면 된다.

## E4B

미측정. WebLLM 공개본에 E4B 용 `lib.wasm` 이 없어 직접 컴파일(emscripten)해야 한다. Task 11 의 E4B 분기를 볼 때 한다.

## 판정 (잠정 — 기계 ② 만으로)

- 선택 도구 → runtime: **webllm** (잠정)
- 이유:
  - 판정 규칙 2: 자격 후보 중 문법 강제가 실제로 동작한 도구는 WebLLM 뿐이다(강제 켬 20/20). 같은 모델·같은 문장인데 강제를 끄면 15/20 으로 떨어진다.
  - 평균 1.4 s 로 합격선 5 s 안이고, 캐시 불러오기 4.6 s 로 두 번째부터 빠르다.
  - MediaPipe 는 4배 빠르지만(319 ms) 문법 강제가 없고(17/20), 모델이 브라우저에 캐시되지 않아 열 때마다 2 GB 를 다시 받는다.
  - wllama 는 CPU 라 문장당 31 s 로 자격(≤ 5 s)이 없고, 문법 강제에서 출력이 깨졌다 → 탈락.
- 남은 위험:
  1. **관리자 PC 미측정.** 이 PC 는 RTX 5070 Ti 라 관리자 PC(내장 그래픽일 가능성)보다 훨씬 빠르다. 관리자 PC 에서 WebLLM 이 5 s 를 넘으면 판정이 바뀐다(규칙 4 — cw 결정).
  2. 메모리 미측정. (변환 경로는 Step 9 에서 통과)
  3. MLC Windows 휠이 `SPIRV-Tools.dll` 없이 배포된다 — 새 nightly 로 바꾸면 같은 손질이 필요할 수 있다.
  4. MediaPipe 를 다시 볼 여지: 문법 강제 없이도 파인튜닝 뒤 규격 통과가 99% 이상이면(합격선 "강제 없음 ≤ 1%") 속도 때문에 더 나을 수 있다. 그러려면 모델 캐시(Cache API·OPFS)를 직접 붙여야 한다.

## 계획서와 다르게 한 것

| 계획서 | 실제 | 이유 |
|---|---|---|
| Step 6: `llama.cpp/examples/json_schema_to_grammar.py` | 커밋 `c5a5535e6ebc` 의 같은 파일 | 최신 llama.cpp 에서 지워짐(`acecd56`, 2026-09-12) |
| Step 6: 생성된 `form.gbnf` 그대로 | 한글 enum 값의 `\uXXXX` 를 글자로 바꿈(28곳) | 생성기가 `json.dumps` 기본값(ensure_ascii)으로 써서, 문법 강제 시 모델이 `"수업"` 을 한글 글자로 못 내고 유니코드 이스케이프(역슬래시 + `u` + 16진수 4자리) 형태로만 낼 수 있었다 |
| Step 6: `python …` | `python -X utf8 …` | Windows 기본 인코딩(cp949)에서 한글 스키마를 못 읽고 `make_suite.py` 출력이 깨진다 |
| MediaPipe 기본 모델 `litert-community/gemma-4-e2b-it/…-int4-web.task` | `litert-community/gemma-4-E2B-it-litert-lm/…/gemma-4-E2B-it-web.task` | 계획서 주소는 401(없는 저장소) |
| MediaPipe 대화 틀 `<start_of_turn>…` (Gemma 3) | `<|turn>system … <turn|>` (Gemma 4, 모델 저장소의 `chat_template.jinja`) | 계획서 주석이 예고한 "chat template 과 다르면 PROMPT 한 줄만 고친다" 경우 |
| Step 7: HF Space (조직 계정) | wj 개인 계정에 공개 — https://huggingface.co/spaces/leemonta9482/esc-spike (직접 주소 https://leemonta9482-esc-spike.static.hf.space) | 조직(spec §17) 미정 — 계획서대로 개인 계정. 직접 주소에서 `webgpu: true`·`cross_origin_isolated: true` 확인 |
| Step 8: 기계 2대 × 4개, Chrome 작업 관리자로 메모리 | 기계 ② 만, Playwright 자동화 Chrome, 메모리 미측정 | 관리자 PC 사용 불가. 자동화 브라우저에서는 작업 관리자 값을 읽을 수 없다 |
| Step 8: wllama 20문장 | 3문장 뒤 중단 | 문장당 31 s(합격선 6배) + 출력 깨짐 — 결론이 바뀌지 않아 10분을 더 쓰지 않음 |
| Step 9: 1·2위 변환 확인 | 1위(WebLLM)만 | 1위가 통과해 2위 확인은 판정을 바꾸지 않는다 |
| Task 10 갈래 B: `mlc_llm compile --device webgpu` (emscripten) | 공개 `lib.wasm` 재사용 | 같은 구조·양자화면 같은 라이브러리 — 출력 20/20 일치로 확인 |
