# 관리자 AI 비서 ② 모델 — 실행 도구 실험 · 학습 데이터 · 파인튜닝 · 평가 · 변환 · 배포 (plan)

<!-- 배치: docs/plans/2026-11-25-ai-assistant-02-finetune.md -->

- 생성일시: 2026-11-25
- 기준 spec: `docs/specs/2026-11-25-admin-ai-assistant-design.md` (§8)
- 공통 부록: `docs/plans/2026-11-25-ai-assistant-00-interfaces.md` — 양식·프롬프트·`assistant_proto` API·모델 안내 키는 **부록 그대로** 쓴다
- 담당: wj @leemonta9482 (`ml/`). 합격선 확인·릴리스 머지는 cw @ssenu
- 브랜치: `wj` 에서 `feature/ml-spike`(Task 1), `feature/ml-pipeline`(Task 2~7), `feature/ml-train`(Task 8~10), `feature/ml-release-vN`(Task 11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 문장을 양식 JSON 으로 옮기는 Gemma 4 E2B 파인튜닝 모델을 만들고, 합격선을 넘긴 양자화 모델을 Hugging Face 에 올려 서버 모델 안내(`server/app/assistant/model.json`)로 배포한다.

**Architecture:** 정답이 확실한 데이터를 기계로 만든다 — 문장 틀 × 가상 값 생성기 → Claude 다양화(해석기로 뜻이 같은 변형만 남김). 사람이 쓴 문장 약 300개는 시험에만 쓴다. 학습은 LoRA SFT(TRL·PEFT), 평가는 `assistant_proto` 해석기로 "푼 값"을 비교하는 채점기 하나로 HF 실행·브라우저 실행을 똑같이 채점한다. 브라우저 실행 도구는 0단계 실험으로 고르고, 그 도구 형식으로 변환·양자화한 **배포 모델**로 합격 판정한다.

**Tech Stack:** Python 3.12 · uv · ruff · pytest · `assistant-proto`(경로 의존) · transformers / TRL / PEFT / datasets / bitsandbytes(학습, 선택 설치) · anthropic 공식 SDK(다양화, 선택 설치) · huggingface_hub(배포, 선택 설치) · 브라우저 하네스: 순수 ES module + WebLLM / Transformers.js / MediaPipe tasks-genai / wllama · Kaggle 또는 Colab GPU(16 GB)

## Global Constraints

- 합격선(사람 시험 문장 + 계약 예문, **배포할 양자화 모델** 기준): intent 정확도 ≥ 97% · 칸 정확도(해석기로 푼 값 기준) ≥ 95% · 양식 전체 일치 ≥ 90% · 형식 오류 0%(문법 강제) / ≤ 1%(강제 없음) · 위험 오류(추가·수정·승인 → 삭제·거절) ≤ 0.5% · 응답 시간(학과 관리자 PC, 문장 1개 평균) ≤ 5초.
- 모델 출력 = `assistant_proto.canonical_json(form)` 한 줄. 입력 = 시스템 `SYSTEM_PROMPT` + 사용자 `접두어 + 문장`(첫 턴 `FIRST_PREFIX`, 이어지는 턴 `render_prefix(...)`). Gemma 4 생각 모드는 끈다. 생성 `temperature 0`, `max_tokens 256`.
- 학습·다양화·공개 데이터에는 **가상 값만** 쓴다(가상 건물·강의실·과목·교수·학생). 실제 교수·학생 이름은 Hugging Face·외부 API 로 보내지 않는다.
- 사람 시험 문장(`ml/data/test_human.jsonl`)과 계약 예문(`assistant_proto/vectors/forms.v1.jsonl`)은 **학습·검증·예문 몇 개(few-shot)에 절대 넣지 않는다.** 시험 문장은 실명을 가상 이름으로 바꾼 뒤에만 커밋한다.
- 모델 가중치·체크포인트·변환 산출물·생성 데이터 원본은 커밋하지 않는다(`ml/.gitignore`). 공개 위치는 Hugging Face 뿐이다.
- Hugging Face·Anthropic·GitHub 토큰은 커밋하지 않는다. 로컬은 환경변수, Kaggle 은 Secrets.
- 비용이 드는 다양화 실행은 `--yes` 없이는 API 를 부르지 않는다. 처음 실행 전에 예상 비용을 cw 에게 보이고 승인받는다.
- 규격 판(`SCHEMA_VERSION`)이 바뀌면 데이터 재생성 + 재학습. 모델 안내의 `schema_v` 와 학습에 쓴 판이 같아야 한다.
- 릴리스는 커밋 해시로 고정한 판만. `model.json` 을 바꾸는 PR 은 cw 가 합격선 숫자를 확인한 뒤 머지한다.
- 커밋: Conventional Commits `feat(ml): …`(CI 는 `chore(infra): …`), attribution 줄 없음, `git add` 는 정확한 파일만.

## 선행 조건 한눈에

| Task | 선행 조건 |
|---|---|
| 1 (0단계 실험) | **없음 — 바로 시작** |
| 2~7 (뼈대·생성기·다양화·시험 세트·채점기·예측기) | 01 의 **PR A(`assistant_proto/`) 머지** |
| 8 (기준 점수) | Task 5·6·7 + GPU |
| 9 (학습) | Task 3·4 + GPU |
| 10 (변환·양자화 평가) | Task 1 판정 + Task 9 |
| 11 (릴리스) | Task 10 합격 + 01 의 `server/app/assistant/model.json` 존재 + HF 조직 결정(spec §17) |
| 12 (게이트·PR) | 각 PR 마다 |

## 파일 구조

```
ml/
├── pyproject.toml          # esc-ml. 기본 의존 = assistant-proto 만. 학습·다양화·배포는 optional extras
├── uv.lock
├── README.md
├── .gitignore
├── esc_ml/
│   ├── __init__.py
│   ├── records.py          # Example·Prediction 레코드, JSONL 읽기·쓰기, 문장 속 표현 검사, 계약 예문 읽기
│   ├── gates.py            # 합격선 상수
│   ├── gen/
│   │   ├── __init__.py
│   │   ├── __main__.py     # python -m esc_ml.gen
│   │   ├── values.py       # 가상 값
│   │   ├── templates.py    # 문장 틀 (train/val 분리)
│   │   └── build.py        # 틀 × 값 → Example
│   ├── paraphrase.py       # Claude 다양화 + 해석기 검증
│   ├── label.py            # 사람 시험 문장 라벨링 CLI
│   ├── overlap.py          # 시험 ↔ 학습 겹침 검사
│   ├── score.py            # 채점기 + 보고서
│   ├── agree.py            # 두 예측 묶음 일치 비교(양자화 전후)
│   ├── suite.py            # 브라우저 하네스용 묶음 만들기
│   ├── hf.py               # transformers 모델 불러오기
│   ├── predict_hf.py       # HF 실행 예측
│   ├── train.py            # LoRA SFT
│   ├── merge.py            # LoRA 병합
│   └── release.py          # 파일 목록·SHA-256, model.json, 모델 카드, HF 업로드
├── spike/                  # 브라우저 하네스 (정적 파일, HF Space 로도 올림)
│   ├── README.md           # HF Space 머리(front matter) 겸 설명
│   ├── index.html
│   ├── common.js
│   ├── adapters/{webllm,transformers,mediapipe,wllama}.js
│   ├── form.schema.json    # 0단계용 임시 스키마(부록 §1 그대로)
│   ├── system_draft.txt    # 0단계용 임시 지시문
│   ├── spike_examples.jsonl
│   ├── make_suite.py
│   ├── serve.py
│   └── suites/spike.json
├── notebooks/kaggle_train.md
├── data/test_human.jsonl   # 커밋 (가상화 후)
├── reports/                # 커밋 (spike.md, baseline-*.md, run-*.md, release-*.md)
└── tests/
```

## 레코드 모양 (이 작업지시서 안의 약속)

`Example` JSONL 한 줄:
```json
{"id": "g7-t000001", "split": "train", "template": "event.add/01", "now": "2026-11-03T10:15:00+09:00",
 "prefix": "관리자: ", "utterance": "803 금요일 15시부터 18시까지 특강 예약해줘",
 "form": {"v": 1, "intent": "event.add", "target": {}, "set": {"rooms": ["803"], "when": "금요일", "time": "15시부터 18시까지", "type": "특강"}}}
```
`Prediction` JSONL 한 줄(HF 예측기·브라우저 하네스 공통): `{"id": "…", "text": "<모델 출력 그대로>", "latency_ms": 1234}`. 다른 키가 더 있어도 읽을 때 무시한다.

---

### Task 1: 0단계 — 브라우저 실행 도구 실험 (선행 조건 없음)

**Files:**
- Create: `ml/spike/README.md`, `ml/spike/index.html`, `ml/spike/common.js`, `ml/spike/adapters/webllm.js`, `ml/spike/adapters/transformers.js`, `ml/spike/adapters/mediapipe.js`, `ml/spike/adapters/wllama.js`, `ml/spike/form.schema.json`, `ml/spike/system_draft.txt`, `ml/spike/spike_examples.jsonl`, `ml/spike/make_suite.py`, `ml/spike/serve.py`, `ml/spike/suites/spike.json`(생성물이지만 커밋 — 0단계 기록용), `ml/reports/spike.md`
- Create: `ml/.gitignore` (이 Task 에서 먼저 만든다 — Task 2 가 이어서 쓴다)

**Interfaces:**
- Produces: 하네스 어댑터 모양 `load(model: string, onProgress(p: number, text?: string)) → Promise<void>`, `generate(system: string, user: string, constraint: Suite | null) → Promise<{text: string, tokens: number | null}>`, `supportsGrammar: boolean`, 선택 `defaultModel() → Promise<string>`. 묶음(Suite) JSON `{system_prompt, json_schema, gbnf, examples: [{id, user, gold}]}` — Task 7 의 `esc_ml.suite` 가 같은 모양을 만든다. 예측 내보내기 = `Prediction` JSONL.
- Produces: `ml/reports/spike.md` 의 **선택 도구** 한 줄(`runtime: webllm | transformers | litert | wllama`) — Task 10·11 이 이 값으로 갈래를 고른다. MediaPipe tasks-genai 로 잰 결과는 `litert` 로 적는다(같은 LiteRT 계열 모델 파일·구글 공식 경로).

- [ ] **Step 1: `.gitignore`**

`ml/.gitignore`:
```gitignore
# 생성·다양화 데이터 원본 (HF 데이터 저장소에만)
data/gen/
data/para/
data/raw/
# 학습·변환·예측 산출물
runs/
out/
preds/
spike/models/
spike/suites/*
!spike/suites/spike.json
# 대용량 모델 파일은 어디에 있든 커밋하지 않는다
*.safetensors
*.gguf
*.onnx
*.onnx_data
*.wasm
*.task
*.litertlm
*.bin
.env
```

- [ ] **Step 2: 임시 스키마·지시문·예문**

`ml/spike/form.schema.json` — 부록 §1 을 그대로 옮긴 0단계용 스키마(`$ref` 를 못 읽는 문법 엔진이 있어 칸 정의를 두 번 펼쳐 쓴다). PR A 머지 뒤에는 `assistant_proto.json_schema()` 를 쓴다(Task 7).
```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["v", "intent", "target", "set"],
  "properties": {
    "v": {"type": "integer", "enum": [1]},
    "intent": {"type": "string", "enum": [
      "event.add", "event.change", "event.remove",
      "exam.add", "exam.change", "exam.remove",
      "class.add", "class.change", "class.remove",
      "request.approve", "request.reject",
      "ask.free_rooms", "ask.schedule", "ask.requests", "ask.node",
      "fill", "cancel", "unknown"]},
    "target": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "rooms": {"type": "array", "minItems": 1, "maxItems": 30, "items": {"type": "string", "minLength": 1, "maxLength": 20}},
        "when": {"type": "string", "minLength": 1, "maxLength": 40},
        "time": {"type": "string", "minLength": 1, "maxLength": 40},
        "type": {"type": "string", "enum": ["수업", "시험", "휴강", "빈강의실", "특강", "대여"]},
        "subject": {"type": "string", "minLength": 1, "maxLength": 40},
        "professor": {"type": "string", "minLength": 1, "maxLength": 20},
        "reason": {"type": "string", "minLength": 1, "maxLength": 100},
        "requester": {"type": "string", "minLength": 1, "maxLength": 20}
      }
    },
    "set": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "rooms": {"type": "array", "minItems": 1, "maxItems": 30, "items": {"type": "string", "minLength": 1, "maxLength": 20}},
        "when": {"type": "string", "minLength": 1, "maxLength": 40},
        "time": {"type": "string", "minLength": 1, "maxLength": 40},
        "type": {"type": "string", "enum": ["수업", "시험", "휴강", "빈강의실", "특강", "대여"]},
        "subject": {"type": "string", "minLength": 1, "maxLength": 40},
        "professor": {"type": "string", "minLength": 1, "maxLength": 20},
        "reason": {"type": "string", "minLength": 1, "maxLength": 100},
        "requester": {"type": "string", "minLength": 1, "maxLength": 20}
      }
    }
  }
}
```

`ml/spike/system_draft.txt` (0단계 전용 임시 지시문 — 실제 지시문은 `assistant_proto.SYSTEM_PROMPT`):
```text
너는 대학 강의실 관리 AI 비서의 입력 해석기다. 관리자의 문장을 아래 양식의 JSON 한 줄로만 바꿔 출력한다. 설명·코드블록 없이 JSON 만 출력한다.
양식: {"v":1,"intent":…,"target":{…},"set":{…}}
intent: event.add event.change event.remove exam.add exam.change exam.remove class.add class.change class.remove request.approve request.reject ask.free_rooms ask.schedule ask.requests ask.node fill cancel unknown 중 하나.
target 은 찾을 대상, set 은 새 값. 칸: rooms(강의실 표현 목록) when(날짜·기간·요일 표현) time(시각 표현) type(수업|시험|휴강|빈강의실|특강|대여) subject professor reason requester.
강의실·날짜·시각·이름은 문장에 나온 글자 그대로 옮기고 계산하지 않는다. 없는 칸은 뺀다. 지원하지 않는 요청은 unknown, 취소는 cancel. "상태:" 줄이 있으면 관리자가 질문에 답한 것이므로 바뀐 칸만 fill 로 낸다.
예: 관리자: 803 금요일 3시부터 6시 세미나 → {"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"],"when":"금요일","time":"3시부터 6시","type":"특강"}}
예: 관리자: 801 시험기간 없애줘 → {"v":1,"intent":"exam.remove","target":{"rooms":["801"]},"set":{}}
```

`ml/spike/spike_examples.jsonl` (20줄 — 0단계 속도·형식 측정용, 정확도 판정용 아님):
```jsonl
{"id":"s01","user":"관리자: 803호 이번주 금요일 15시부터 18시까지 특강 예약해줘","gold":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803호"],"when":"이번주 금요일","time":"15시부터 18시까지","type":"특강"}}}
{"id":"s02","user":"관리자: 다음 주 화요일 공학관 801 자료구조 휴강","gold":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["공학관 801"],"when":"다음 주 화요일","type":"휴강","subject":"자료구조"}}}
{"id":"s03","user":"관리자: 801·803 12/15~19 시험기간 잡아줘","gold":{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["801","803"],"when":"12/15~19"}}}
{"id":"s04","user":"관리자: 803 월 9시부터 12시까지 운영체제 김하늘 교수님 수업 추가","gold":{"v":1,"intent":"class.add","target":{},"set":{"rooms":["803"],"when":"월","time":"9시부터 12시까지","subject":"운영체제","professor":"김하늘"}}}
{"id":"s05","user":"관리자: 금요일 오후 빈 강의실 있어?","gold":{"v":1,"intent":"ask.free_rooms","target":{"when":"금요일","time":"오후"},"set":{}}}
{"id":"s06","user":"관리자: 801 배터리 몇 퍼센트야?","gold":{"v":1,"intent":"ask.node","target":{"rooms":["801"]},"set":{}}}
{"id":"s07","user":"관리자: 대기 중인 신청 보여줘","gold":{"v":1,"intent":"ask.requests","target":{},"set":{}}}
{"id":"s08","user":"관리자: 803 목요일 알고리즘 특강 16시로 바꿔줘","gold":{"v":1,"intent":"event.change","target":{"rooms":["803"],"when":"목요일","subject":"알고리즘 특강"},"set":{"time":"16시로"}}}
{"id":"s09","user":"관리자: 803 금요일 취업 설명회 취소해줘","gold":{"v":1,"intent":"event.remove","target":{"rooms":["803"],"when":"금요일","subject":"취업 설명회"},"set":{}}}
{"id":"s10","user":"관리자: 홍길동 신청 승인해줘","gold":{"v":1,"intent":"request.approve","target":{"requester":"홍길동"},"set":{}}}
{"id":"s11","user":"관리자: 801 내일 신청 거절해줘. 사유는 장비 점검","gold":{"v":1,"intent":"request.reject","target":{"rooms":["801"],"when":"내일"},"set":{"reason":"장비 점검"}}}
{"id":"s12","user":"관리자: 803 시험기간 없애줘","gold":{"v":1,"intent":"exam.remove","target":{"rooms":["803"]},"set":{}}}
{"id":"s13","user":"관리자: 점심 뭐 먹지","gold":{"v":1,"intent":"unknown","target":{},"set":{}}}
{"id":"s14","user":"상태: event.add | 강의실 803 | 날짜 11/27(금) | 시각 15:00~18:00 | 유형 특강 | 이름 ?\n질문: 특강 이름은 무엇인가요?\n관리자: 취소","gold":{"v":1,"intent":"cancel","target":{},"set":{}}}
{"id":"s15","user":"상태: event.add | 강의실 803 | 날짜 11/27(금) | 시각 15:00~18:00 | 유형 특강 | 이름 ?\n질문: 특강 이름은 무엇인가요?\n관리자: 알고리즘 특강이요","gold":{"v":1,"intent":"fill","target":{},"set":{"subject":"알고리즘 특강"}}}
{"id":"s16","user":"상태: event.add | 강의실 801 | 날짜 12/2(수) | 시각 ? | 유형 대여 | 이름 동아리 회의\n질문: 몇 시부터 몇 시까지인가요?\n관리자: 3시부터 6시","gold":{"v":1,"intent":"fill","target":{},"set":{"time":"3시부터 6시"}}}
{"id":"s17","user":"관리자: 8층 전체 12/24 휴강","gold":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["8층 전체"],"when":"12/24","type":"휴강"}}}
{"id":"s18","user":"관리자: 803 화목 10시 반부터 12시 대관","gold":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"],"when":"화목","time":"10시 반부터 12시","type":"대여"}}}
{"id":"s19","user":"관리자: 공학관 803 월요일 데이터베이스 수업 빼줘","gold":{"v":1,"intent":"class.remove","target":{"rooms":["공학관 803"],"when":"월요일","subject":"데이터베이스"},"set":{}}}
{"id":"s20","user":"관리자: 803 시간표 보여줘","gold":{"v":1,"intent":"ask.schedule","target":{"rooms":["803"]},"set":{}}}
```

- [ ] **Step 3: 묶음 만들기·로컬 서버 스크립트**

`ml/spike/make_suite.py` (표준 라이브러리만 — `assistant_proto` 가 없어도 돈다):
```python
"""0단계 묶음(suites/spike.json) 만들기 — 임시 지시문·스키마·20문장. form.gbnf 가 있으면 함께 넣는다."""

import json
import pathlib

HERE = pathlib.Path(__file__).parent


def main() -> None:
    lines = (HERE / "spike_examples.jsonl").read_text(encoding="utf-8").splitlines()
    examples = [json.loads(line) for line in lines if line.strip()]
    gbnf_path = HERE / "form.gbnf"
    suite = {
        "system_prompt": (HERE / "system_draft.txt").read_text(encoding="utf-8").strip(),
        "json_schema": json.loads((HERE / "form.schema.json").read_text(encoding="utf-8")),
        "gbnf": gbnf_path.read_text(encoding="utf-8") if gbnf_path.exists() else None,
        "examples": examples,
    }
    out = HERE / "suites" / "spike.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(suite, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out} — {len(examples)}문장, gbnf={'있음' if suite['gbnf'] else '없음'}")


if __name__ == "__main__":
    main()
```

`ml/spike/serve.py` (멀티스레드 WASM 에 필요한 cross-origin isolation 헤더를 붙여 정적 서빙):
```python
"""하네스 로컬 서버 — python ml/spike/serve.py → http://localhost:8080 (localhost 는 WebGPU 보안 문맥)."""

import functools
import http.server
import pathlib

HERE = pathlib.Path(__file__).parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "credentialless")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(Handler, directory=str(HERE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", 8080), handler) as srv:
        print("http://localhost:8080")
        srv.serve_forever()
```

- [ ] **Step 4: 하네스 화면·공통 로직**

`ml/spike/index.html`:
```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>ESC AI 비서 — 브라우저 실행 도구 실험</title>
<style>
  body { font: 14px system-ui, sans-serif; margin: 24px; max-width: 1200px }
  label { margin-right: 12px }
  table { border-collapse: collapse; width: 100%; margin-top: 12px }
  td, th { border: 1px solid #ccc; padding: 4px 6px; font-size: 12px; vertical-align: top }
  .ok { background: #e4f6e4 } .bad { background: #fde2e2 }
  pre { white-space: pre-wrap; margin: 0 }
</style>
</head>
<body>
<h1>브라우저 실행 도구 실험</h1>
<pre id="env"></pre>
<p>
  <label>도구 <select id="runtime">
    <option value="webllm">WebLLM</option>
    <option value="transformers">Transformers.js</option>
    <option value="mediapipe">MediaPipe tasks-genai (LiteRT 계열)</option>
    <option value="wllama">wllama (llama.cpp)</option>
  </select></label>
  <label>모델 <input id="model" size="80"></label>
</p>
<p>
  <label>묶음 <input id="suite" value="suites/spike.json" size="30"></label>
  <label><input type="checkbox" id="grammar" checked> 문법 강제(지원하는 도구만)</label>
  <button id="load">불러오기</button>
  <button id="run" disabled>실행</button>
  <button id="export" disabled>예측·요약 내보내기</button>
</p>
<p id="status"></p>
<table>
  <thead><tr><th>id</th><th>ms</th><th>토큰</th><th>규격</th><th>20문장 정답</th><th>출력</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<h2>요약</h2>
<pre id="summary"></pre>
<script type="module" src="common.js"></script>
</body>
</html>
```

`ml/spike/common.js`:
```js
// 하네스 공통 — 불러오기 시간, 문장별 응답 시간, 토큰, 규격 통과, 정답 일치를 재고 Prediction JSONL 로 내보낸다.
import Ajv from 'https://esm.sh/ajv@8'

const $ = (id) => document.getElementById(id)
const TOP = ['v', 'intent', 'target', 'set']
const FIELDS = ['rooms', 'when', 'time', 'type', 'subject', 'professor', 'reason', 'requester']
let adapter = null
let suite = null
let results = []
let loadInfo = null

// 부록 §1.3 정규 직렬화(키 순서 고정) — 정답 비교용
function canonical(f) {
  const fx = (o) => Object.fromEntries(FIELDS.filter((k) => o && o[k] !== undefined).map((k) => [k, o[k]]))
  return JSON.stringify(Object.fromEntries(TOP.map((k) => [k, k === 'target' || k === 'set' ? fx(f[k]) : f[k]])))
}

async function envInfo() {
  const gpu = navigator.gpu ? await navigator.gpu.requestAdapter() : null
  const info = gpu?.info ?? {}
  return {
    ua: navigator.userAgent,
    cores: navigator.hardwareConcurrency,
    device_memory_gb: navigator.deviceMemory ?? null,
    webgpu: !!gpu,
    gpu: [info.vendor, info.architecture, info.description].filter(Boolean).join(' / '),
    cross_origin_isolated: self.crossOriginIsolated,
  }
}

async function pickRuntime() {
  adapter = await import(`./adapters/${$('runtime').value}.js`)
  $('model').value = adapter.defaultModel ? await adapter.defaultModel() : ''
}

function download(name, text) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
  a.download = name
  a.click()
}

function percentile(xs, p) {
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.max(0, Math.ceil(p * s.length) - 1)]
}

function summarize() {
  const ms = results.map((r) => r.latency_ms)
  const withTok = results.filter((r) => r.tokens)
  const tps = withTok.length
    ? withTok.reduce((a, r) => a + r.tokens / (r.latency_ms / 1000), 0) / withTok.length
    : null
  return {
    ...loadInfo,
    grammar: $('grammar').checked && adapter.supportsGrammar,
    n: results.length,
    mean_ms: Math.round(ms.reduce((a, b) => a + b, 0) / ms.length),
    p90_ms: percentile(ms, 0.9),
    tokens_per_s: tps === null ? '토큰 수를 못 셈' : Number(tps.toFixed(1)),
    schema_valid: results.filter((r) => r.valid).length,
    exact: results.filter((r) => r.correct).length,
  }
}

$('env').textContent = JSON.stringify(await envInfo(), null, 1)
$('runtime').onchange = pickRuntime
await pickRuntime()

$('load').onclick = async () => {
  suite = await (await fetch($('suite').value)).json()
  const t0 = performance.now()
  try {
    await adapter.load($('model').value, (p, text) => {
      $('status').textContent = `불러오는 중 ${Math.round((p || 0) * 100)}% ${text ?? ''}`
    })
  } catch (e) {
    $('status').textContent = `불러오기 실패: ${e}`
    console.error(e)
    return
  }
  loadInfo = { runtime: $('runtime').value, model: $('model').value, load_ms: Math.round(performance.now() - t0), env: await envInfo() }
  $('status').textContent = `불러오기 ${loadInfo.load_ms} ms (같은 모델을 새로고침 뒤 다시 불러오면 = 캐시 시간)`
  $('run').disabled = false
}

$('run').onclick = async () => {
  const constraint = $('grammar').checked && adapter.supportsGrammar ? suite : null
  const validate = new Ajv({ strict: false }).compile(suite.json_schema)
  results = []
  $('rows').innerHTML = ''
  await adapter.generate(suite.system_prompt, suite.examples[0].user, constraint) // 예열 — 기록하지 않는다
  for (const ex of suite.examples) {
    const t0 = performance.now()
    const out = await adapter.generate(suite.system_prompt, ex.user, constraint)
    const latency = Math.round(performance.now() - t0)
    const text = out.text.trim()
    let parsed = null
    try { parsed = JSON.parse(text) } catch { parsed = null }
    const valid = parsed !== null && validate(parsed)
    const correct = valid && ex.gold !== undefined && canonical(parsed) === canonical(ex.gold)
    results.push({ id: ex.id, text, latency_ms: latency, tokens: out.tokens, valid, correct })
    const tr = document.createElement('tr')
    tr.className = valid ? 'ok' : 'bad'
    for (const v of [ex.id, latency, out.tokens ?? '-', valid ? '통과' : '위반', correct ? '일치' : '-']) {
      const td = document.createElement('td')
      td.textContent = String(v)
      tr.append(td)
    }
    const td = document.createElement('td')
    const pre = document.createElement('pre')
    pre.textContent = text
    td.append(pre)
    tr.append(td)
    $('rows').append(tr)
    $('status').textContent = `${results.length}/${suite.examples.length}`
  }
  $('summary').textContent = JSON.stringify(summarize(), null, 1)
  $('export').disabled = false
}

$('export').onclick = () => {
  const rt = loadInfo.runtime
  download(`preds-${rt}.jsonl`, results.map((r) => JSON.stringify({ id: r.id, text: r.text, latency_ms: r.latency_ms })).join('\n') + '\n')
  download(`run-${rt}.json`, JSON.stringify(summarize(), null, 1))
}
```

- [ ] **Step 5: 어댑터 4개**

`ml/spike/adapters/webllm.js`:
```js
// WebLLM — JSON Schema 문법 강제(response_format). 미리 만든 목록에 Gemma 4 가 없으면 '미지원'으로 기록한다.
// 우리 변환본은 'models/<폴더>' 로 넣는다: 폴더 안에 mlc-chat-config.json·가중치 조각·lib.wasm (Task 10 갈래 B).
import * as webllm from 'https://esm.run/@mlc-ai/web-llm'

export const supportsGrammar = true
let engine = null

export async function defaultModel() {
  const hit = webllm.prebuiltAppConfig.model_list.find((m) => /gemma-?4/i.test(m.model_id))
  return hit ? hit.model_id : ''
}

export async function load(model, onProgress) {
  const custom = model.startsWith('models/') || model.startsWith('http')
  const base = custom ? new URL(model.replace(/\/?$/, '/'), location.href).href : null
  const appConfig = custom
    ? { model_list: [{ model: base, model_id: 'esc-custom', model_lib: base + 'lib.wasm' }] }
    : undefined
  engine = await webllm.CreateMLCEngine(custom ? 'esc-custom' : model, {
    appConfig,
    initProgressCallback: (r) => onProgress(r.progress ?? 0, r.text),
  })
}

export async function generate(system, user, constraint) {
  const r = await engine.chat.completions.create({
    messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
    temperature: 0,
    max_tokens: 256,
    ...(constraint ? { response_format: { type: 'json_object', schema: JSON.stringify(constraint.json_schema) } } : {}),
  })
  return { text: r.choices[0].message.content ?? '', tokens: r.usage?.completion_tokens ?? null }
}
```

`ml/spike/adapters/transformers.js`:
```js
// Transformers.js (ONNX, WebGPU) — 문법 강제 없음. 생각 모드는 chat template 에 enable_thinking:false 로 끈다.
// 우리 변환본은 'models/<폴더>' (Task 10 갈래 C).
import { env, pipeline } from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4'

export const supportsGrammar = false
let gen = null

export async function defaultModel() {
  return 'onnx-community/gemma-4-E2B-it-ONNX'
}

export async function load(model, onProgress) {
  let id = model
  if (model.startsWith('models/')) {
    env.allowLocalModels = true
    env.allowRemoteModels = false
    env.localModelPath = new URL('models/', location.href).href
    id = model.slice('models/'.length)
  }
  gen = await pipeline('text-generation', id, {
    dtype: 'q4f16',
    device: 'webgpu',
    progress_callback: (p) => { if (p.status === 'progress') onProgress(p.progress / 100, p.file) },
  })
}

export async function generate(system, user) {
  const prompt = gen.tokenizer.apply_chat_template(
    [{ role: 'system', content: system }, { role: 'user', content: user }],
    { add_generation_prompt: true, tokenize: false, enable_thinking: false },
  )
  const out = await gen(prompt, { max_new_tokens: 256, do_sample: false, return_full_text: false })
  const text = out[0].generated_text
  return { text, tokens: gen.tokenizer.encode(text).length }
}
```

`ml/spike/adapters/mediapipe.js`:
```js
// MediaPipe tasks-genai LlmInference (LiteRT 계열 .task/.litertlm). 문법 강제 없음.
// MediaPipe LLM Inference 는 유지보수 모드 — 구글은 LiteRT-LM JS 로 옮기라고 안내한다(Step 7 확인 항목).
// generateResponse 는 원문 그대로 받으므로 Gemma 대화 틀을 직접 씌운다. 모델 카드의 chat template 과 다르면 PROMPT 한 줄만 고친다.
import { FilesetResolver, LlmInference } from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-genai'

export const supportsGrammar = false
let llm = null
const PROMPT = (system, user) => `<start_of_turn>user\n${system}\n\n${user}<end_of_turn>\n<start_of_turn>model\n`

export async function defaultModel() {
  return 'https://huggingface.co/litert-community/gemma-4-e2b-it/resolve/main/gemma-4-e2b-it-int4-web.task'
}

export async function load(model, onProgress) {
  const genai = await FilesetResolver.forGenAiTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-genai/wasm')
  onProgress(0, '내려받는 중(진행률 없음)')
  llm = await LlmInference.createFromOptions(genai, {
    baseOptions: { modelAssetPath: model },
    maxTokens: 2048,
    topK: 1,
    temperature: 0,
  })
  onProgress(1, '완료')
}

export async function generate(system, user) {
  const text = await llm.generateResponse(PROMPT(system, user))
  return { text, tokens: llm.sizeInTokens(text) }
}
```

`ml/spike/adapters/wllama.js`:
```js
// wllama (llama.cpp WASM) — GBNF 문법 강제. 업스트림은 CPU(WASM SIMD·멀티스레드)다 — WebGPU 아님을 표에 적는다.
// 모델 칸: GGUF URL. 조각(split)이면 쉼표로 여러 개.
import { Wllama } from 'https://cdn.jsdelivr.net/npm/@wllama/wllama@2/esm/index.js'

const CDN = 'https://cdn.jsdelivr.net/npm/@wllama/wllama@2/esm'
export const supportsGrammar = true
let w = null

export async function load(model, onProgress) {
  w = new Wllama({
    'single-thread/wllama.wasm': `${CDN}/single-thread/wllama.wasm`,
    'multi-thread/wllama.wasm': `${CDN}/multi-thread/wllama.wasm`,
  })
  const urls = model.split(',').map((s) => new URL(s.trim(), location.href).href)
  await w.loadModelFromUrl(urls.length === 1 ? urls[0] : urls, {
    progressCallback: ({ loaded, total }) => onProgress(total ? loaded / total : 0, '내려받는 중'),
  })
}

export async function generate(system, user, constraint) {
  const text = await w.createChatCompletion(
    [{ role: 'system', content: system }, { role: 'user', content: user }],
    { nPredict: 256, sampling: { temp: 0, ...(constraint?.gbnf ? { grammar: constraint.gbnf } : {}) } },
  )
  return { text, tokens: (await w.tokenize(text)).length }
}
```

- [ ] **Step 6: GBNF 만들기·묶음 만들기·로컬 확인**

```bash
git clone --depth 1 https://github.com/ggml-org/llama.cpp ml/out/llama.cpp
python ml/out/llama.cpp/examples/json_schema_to_grammar.py ml/spike/form.schema.json > ml/spike/form.gbnf
python ml/spike/make_suite.py
python ml/spike/serve.py
```
Expected: `ml/spike/suites/spike.json — 20문장, gbnf=있음`, 브라우저 `http://localhost:8080` 에서 환경 정보에 `"webgpu": true` 와 `"cross_origin_isolated": true`.
`form.gbnf` 는 커밋하지 않아도 되지만(묶음에 들어감) 재현을 위해 커밋한다(작은 텍스트 파일 — `.gitignore` 대상 아님).

- [ ] **Step 7: 학과 관리자 PC 용 공개 하네스 (Hugging Face 정적 Space)**

`ml/spike/README.md`:
```markdown
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
```
업로드(토큰은 `HF_TOKEN` 환경변수 또는 `huggingface-cli login`, 조직은 spec §17 결정 — 정해지기 전에는 wj 개인 계정):
```bash
uv run --with huggingface_hub python -c "
from huggingface_hub import HfApi
api = HfApi()
repo = 'HF_OWNER/esc-spike'.replace('HF_OWNER', __import__('os').environ['HF_OWNER'])
api.create_repo(repo, repo_type='space', space_sdk='static', exist_ok=True)
api.upload_folder(folder_path='ml/spike', repo_id=repo, repo_type='space', ignore_patterns=['models/*', '*.gguf', '*.wasm'])
print('https://huggingface.co/spaces/' + repo)
"
```
`HF_OWNER=<계정 또는 조직>` 을 먼저 export 한다. 관리자 PC 에서는 Space 페이지의 "Embed/Direct URL"(정적 Space 직접 주소, `*.static.hf.space`)로 연다 — iframe 안에서는 WebGPU·SharedArrayBuffer 가 막힐 수 있다. 환경 정보의 `cross_origin_isolated` 가 `false` 면 wllama 는 단일 스레드로만 돈다고 표에 적는다.

- [ ] **Step 8: 측정 — 두 기계 × 네 도구**

기계: (1) **학과 관리자 PC**(spec §17 — 안 되면 같은 사양 PC, 표에 "대체"라고 적는다) (2) wj 노트북. 브라우저: Chrome 최신(관리자 PC 기본 브라우저가 Edge 면 Edge 도).

도구마다:
1. 브라우저 캐시 비우기(개발자 도구 → Application → Clear site data) → [불러오기] → **첫 다운로드 시간** = 상태 줄의 ms.
2. 새로고침 → [불러오기] → **캐시 불러오기 시간**.
3. [실행] (문법 강제 켬, 지원 도구만) → 요약의 `mean_ms`·`p90_ms`·`tokens_per_s`·`schema_valid`·`exact`.
4. 실행 중 Chrome 작업 관리자(Shift+Esc)의 **탭 메모리 + GPU 프로세스 메모리** 최댓값.
5. 개발자 도구 콘솔의 오류·경고 첫 줄.
6. [예측·요약 내보내기] → `run-<도구>.json`·`preds-<도구>.jsonl` 을 `ml/reports/spike/<기계>/` 에 저장(커밋).
7. 문법 강제 지원 도구는 강제를 **끄고** 한 번 더 [실행] → `schema_valid` 차이를 적는다.

모델 칸 값: WebLLM = `defaultModel()` 이 채운 값(비면 "미지원"), Transformers.js = `onnx-community/gemma-4-E2B-it-ONNX`, MediaPipe = 기본값 `.task` URL, wllama = Hugging Face 에서 "gemma-4-E2B-it GGUF" 로 찾은 Q4_K_M 파일 URL(`https://huggingface.co/<저장소>/resolve/main/<파일>.gguf`, 표에 저장소 이름 기록).

추가: 1위 후보 도구로 **E4B** 도 관리자 PC 에서 1·3 만 잰다(Task 11 의 E4B 분기 판단용).

LiteRT-LM JS: https://developers.google.com/edge/litert-lm/js 를 열어 Gemma 4 E2B 웹 모델 목록·문법 강제 지원 여부를 확인해 표의 "비고"에 적는다(MediaPipe 하네스 결과와 같은 모델 파일 계열).

- [ ] **Step 9: 변환 경로 사전 확인 (1·2위 후보만)**

튜닝한 모델을 그 도구 형식으로 바꿀 수 없으면 그 도구는 쓸 수 없다. **원본** `google/gemma-4-E2B-it` 를 Task 10 의 해당 갈래 명령으로 직접 변환해 `ml/spike/models/` 에 두고 하네스에서 불러와 [실행]까지 되는지 본다. 실패하면 실패한 명령과 오류 첫 줄을 표에 적고 그 후보를 탈락시킨다.

- [ ] **Step 10: 결과 문서와 판정**

`ml/reports/spike.md`:
```markdown
# 0단계 — 브라우저 실행 도구 실험 결과

- 날짜: YYYY-MM-DD / 측정: wj
- 기계 ①: 학과 관리자 PC (또는 대체: 사양) — CPU / 메모리 / GPU(환경 정보 gpu) / 브라우저
- 기계 ②: wj 노트북 — CPU / 메모리 / GPU / 브라우저

## 기계 ① 학과 관리자 PC

| 항목 | WebLLM | Transformers.js | MediaPipe (LiteRT) | wllama |
|---|---|---|---|---|
| 불러오기 성공 | | | | |
| 첫 다운로드 (s) | | | | |
| 캐시 불러오기 (s) | | | | |
| 평균 응답 mean_ms / p90_ms | | | | |
| 초당 토큰 | | | | |
| 문법 강제 지원 / 켰을 때 규격 통과 (20) | | | | |
| 강제 끔 규격 통과 (20) | | | | |
| 20문장 정답 일치 (참고) | | | | |
| 최대 메모리 (탭 + GPU, MB) | | | | |
| 콘솔 오류 | | | | |
| 변환 경로 사전 확인 (Step 9) | | | | |
| 비고 | | | | |

## 기계 ② wj 노트북
(같은 표)

## E4B (1위 도구, 관리자 PC)
| 첫 다운로드 (s) | mean_ms / p90_ms |
|---|---|

## 판정
- 선택 도구 → runtime: <webllm | transformers | litert | wllama>
- 이유:
- 남은 위험:
```

판정 규칙(순서대로):
1. **후보 자격**: 관리자 PC 에서 불러오기 성공 + 평균 응답 ≤ 5,000 ms + Step 9 변환 경로 통과.
2. 자격 후보 중 **문법 강제가 동작하는 도구**(강제 켬 규격 통과 20/20)가 1순위.
3. 같으면 관리자 PC `mean_ms` 가 작은 쪽, 그다음 첫 다운로드 시간이 작은 쪽.
4. 자격 후보가 없으면: 문법 강제 도구 중 가장 빠른 것을 적고 **cw 에게 바로 알린다**(spec §16 응답 시간 기준 위험 — 2단계 "서버 측 대체 실행" 앞당김 여부는 cw 결정).

- [ ] **Step 11: 커밋 (PR ① — `assistant_proto` 와 무관, 바로 올림)**

```bash
git add ml/.gitignore ml/spike/README.md ml/spike/index.html ml/spike/common.js \
  ml/spike/adapters/webllm.js ml/spike/adapters/transformers.js ml/spike/adapters/mediapipe.js ml/spike/adapters/wllama.js \
  ml/spike/form.schema.json ml/spike/form.gbnf ml/spike/system_draft.txt ml/spike/spike_examples.jsonl \
  ml/spike/make_suite.py ml/spike/serve.py ml/spike/suites/spike.json \
  ml/reports/spike.md ml/reports/spike
git commit -m "feat(ml): 0단계 — 브라우저 실행 도구 실험 하네스와 측정 결과"
```

---

### Task 2: `ml/` 뼈대 — uv 프로젝트, 레코드, CI (선행: PR A 머지)

**Files:**
- Create: `ml/pyproject.toml`, `ml/uv.lock`(생성), `ml/README.md`, `ml/esc_ml/__init__.py`, `ml/esc_ml/records.py`, `ml/esc_ml/gates.py`, `ml/tests/__init__.py`, `ml/tests/test_records.py`
- Modify: `.github/workflows/ci.yml` (changes 필터에 `ml`, 새 `ml` job)

**Interfaces:**
- Consumes: `assistant_proto` — `FIRST_PREFIX`, `SYSTEM_PROMPT`, `canonical_json`, `parse_form`, `FormError`
- Produces (`esc_ml.records`):
  - `Example(id, split, template, now, prefix, utterance, form)` — frozen dataclass, `.user_text() -> str`, `.messages() -> list[dict]`
  - `Prediction(id, text, latency_ms=None)`
  - `read_examples(path) -> list[Example]`, `write_examples(path, rows) -> None`
  - `read_predictions(path) -> dict[str, Prediction]`, `write_predictions(path, preds) -> None`
  - `SPAN_FIELDS: tuple[str, ...]`, `span_values(form: dict) -> list[str]`, `missing_spans(utterance: str, form: dict) -> list[str]`
  - `load_vectors(path) -> list[Example]` — 계약 예문(`assistant_proto/vectors/forms.v1.jsonl`)을 Example 로
- Produces (`esc_ml.gates`): `INTENT_MIN, FIELD_MIN, EXACT_MIN, FORMAT_MAX_GRAMMAR, FORMAT_MAX_FREE, DANGER_MAX, LATENCY_MAX_MS`

- [ ] **Step 1: 프로젝트 파일**

`ml/pyproject.toml`:
```toml
[project]
name = "esc-ml"
version = "0.1.0"
description = "관리자 AI 비서 모델 — 학습 데이터 생성·다양화·파인튜닝·평가·변환·배포"
requires-python = ">=3.12"
dependencies = ["assistant-proto"]

[project.optional-dependencies]
# 무거운 것은 선택 설치 — CI·채점은 기본 의존만으로 돈다
paraphrase = ["anthropic>=1.0"]
train = [
  "torch>=2.5",
  "transformers>=4.56",
  "trl>=0.20",
  "peft>=0.15",
  "accelerate>=1.6",
  "datasets>=3.6",
  "bitsandbytes>=0.46; sys_platform == 'linux'",
]
release = ["huggingface_hub>=0.34"]

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.7"]

[tool.uv.sources]
assistant-proto = { path = "../assistant_proto", editable = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["esc_ml"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`ml/README.md`:
```markdown
# ml — 관리자 AI 비서 모델 (wj)

문장 → 양식 JSON 으로 옮기는 Gemma 4 E2B 파인튜닝. 규격·프롬프트·해석기는 `../assistant_proto/` 가 원본이다.
작업지시서: `docs/plans/2026-11-25-ai-assistant-02-finetune.md`

| 할 일 | 명령 (ml/ 에서) |
|---|---|
| 설치 (채점·생성만) | `uv sync` |
| 설치 (학습) | `uv sync --extra train` |
| 예문 생성 | `uv run python -m esc_ml.gen --n 8000 --seed 7 --out data/gen` |
| 다양화 (비용 — 승인 후) | `uv run --extra paraphrase python -m esc_ml.paraphrase --in data/gen/train.jsonl --out data/para/train.jsonl --yes` |
| 시험 문장 라벨 | `uv run python -m esc_ml.label --csv data/raw/human.csv --out data/test_human.jsonl` |
| 겹침 검사 | `uv run python -m esc_ml.overlap --test data/test_human.jsonl --train data/gen/train.jsonl data/para/train.jsonl` |
| HF 예측 | `uv run --extra train python -m esc_ml.predict_hf …` |
| 채점 | `uv run python -m esc_ml.score …` |
| 하네스 | `python spike/serve.py` → http://localhost:8080 |

데이터 원본·모델·변환 산출물은 커밋하지 않는다(`.gitignore`). 공개는 Hugging Face 에만.
```

- [ ] **Step 2: 실패 테스트**

`ml/tests/__init__.py`: 빈 파일.

`ml/tests/test_records.py`:
```python
from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json

from esc_ml.records import (
    Example,
    Prediction,
    load_vectors,
    missing_spans,
    read_examples,
    read_predictions,
    span_values,
    write_examples,
    write_predictions,
)

EX = Example(
    id="t1",
    split="train",
    template="event.add/01",
    now="2026-11-25T10:00:00+09:00",
    prefix=FIRST_PREFIX,
    utterance="803 금요일 15시부터 18시까지 특강 예약해줘",
    form={
        "v": 1,
        "intent": "event.add",
        "target": {},
        "set": {"rooms": ["803"], "when": "금요일", "time": "15시부터 18시까지", "type": "특강"},
    },
)


def test_examples_roundtrip(tmp_path):
    p = tmp_path / "a.jsonl"
    write_examples(p, [EX])
    assert read_examples(p) == [EX]


def test_messages_shape():
    msgs = EX.messages()
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert msgs[1]["content"] == FIRST_PREFIX + EX.utterance
    assert msgs[2]["content"] == canonical_json(EX.form)


def test_span_values_and_missing():
    assert span_values(EX.form) == ["803", "금요일", "15시부터 18시까지"]
    assert missing_spans(EX.utterance, EX.form) == []
    bad = dict(EX.form, set={**EX.form["set"], "when": "목요일"})
    assert missing_spans(EX.utterance, bad) == ["목요일"]


def test_predictions_roundtrip_and_extra_keys(tmp_path):
    p = tmp_path / "p.jsonl"
    write_predictions(p, [Prediction("t1", '{"v":1}', 1200.0)])
    p.write_text(p.read_text(encoding="utf-8") + '{"id":"t2","text":"x","valid":false}\n', encoding="utf-8")
    got = read_predictions(p)
    assert got["t1"] == Prediction("t1", '{"v":1}', 1200.0)
    assert got["t2"] == Prediction("t2", "x", None)


def test_load_vectors_defaults(tmp_path):
    p = tmp_path / "forms.v1.jsonl"
    p.write_text(
        '{"id": "a", "utterance": "801 시험기간 없애줘", '
        '"form": {"v": 1, "intent": "exam.remove", "target": {"rooms": ["801"]}, "set": {}}}\n',
        encoding="utf-8",
    )
    (ex,) = load_vectors(p)
    assert ex.id == "v-a" and ex.split == "test" and ex.template == "vector"
    assert ex.prefix == FIRST_PREFIX and ex.now.endswith("+09:00")
```

Run: `cd ml && uv sync && uv run pytest tests/test_records.py -q` → FAIL (`ModuleNotFoundError: esc_ml.records`).

- [ ] **Step 3: 구현**

`ml/esc_ml/__init__.py`:
```python
"""관리자 AI 비서 모델 — 데이터·학습·평가·배포 (작업지시서 02)."""
```

`ml/esc_ml/records.py`:
```python
"""예문·예측 레코드 — 생성·다양화·사람 시험·계약 예문·예측이 모두 이 모양을 쓴다."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json

# 문장 속 표현을 그대로 옮기는 칸 (type 만 고르는 칸이라 빠진다 — 부록 §1.1)
SPAN_FIELDS = ("rooms", "when", "time", "subject", "professor", "reason", "requester")
DEFAULT_NOW = "2026-11-25T10:00:00+09:00"


@dataclass(frozen=True)
class Example:
    id: str
    split: str  # train | val | test
    template: str  # 생성 틀 id. 사람 문장 "human", 계약 예문 "vector", 다양화는 "<틀>+p"
    now: str  # 기준 시각 ISO 8601 (KST +09:00) — 채점에서 상대 날짜를 풀 때 쓴다
    prefix: str  # FIRST_PREFIX 또는 render_prefix(...) 결과
    utterance: str
    form: dict  # 정답 양식 (없는 칸은 키를 뺀 dict)

    def user_text(self) -> str:
        return self.prefix + self.utterance

    def messages(self) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self.user_text()},
            {"role": "assistant", "content": canonical_json(self.form)},
        ]


@dataclass(frozen=True)
class Prediction:
    id: str
    text: str  # 모델 출력 그대로
    latency_ms: float | None = None


def _lines(path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _write_lines(path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_examples(path) -> list[Example]:
    return [Example(**r) for r in _lines(path)]


def write_examples(path, rows) -> None:
    _write_lines(path, [asdict(r) for r in rows])


def read_predictions(path) -> dict[str, Prediction]:
    out = {}
    for r in _lines(path):
        out[r["id"]] = Prediction(r["id"], r["text"], r.get("latency_ms"))
    return out


def write_predictions(path, preds) -> None:
    _write_lines(path, [asdict(p) for p in preds])


def span_values(form: dict) -> list[str]:
    out: list[str] = []
    for side in ("target", "set"):
        for key in SPAN_FIELDS:
            v = form.get(side, {}).get(key)
            if v is None:
                continue
            out += list(v) if key == "rooms" else [v]
    return out


def missing_spans(utterance: str, form: dict) -> list[str]:
    """정답 표현 중 문장에 글자 그대로 없는 것 — 생성기·다양화·라벨링의 공통 검사."""
    return [v for v in span_values(form) if v not in utterance]


def load_vectors(path) -> list[Example]:
    """계약 예문 → Example. 줄 모양은 Example 키(id·now·prefix·utterance·form)를 따르고, 없는 키는 기본값."""
    rows = []
    for i, r in enumerate(_lines(path)):
        rows.append(
            Example(
                id=f"v-{r.get('id', i)}",
                split="test",
                template="vector",
                now=r.get("now", DEFAULT_NOW),
                prefix=r.get("prefix", FIRST_PREFIX),
                utterance=r["utterance"],
                form=r["form"],
            )
        )
    return rows
```

`ml/esc_ml/gates.py`:
```python
"""합격선 (spec §8.3) — 배포할 양자화 모델 기준."""

INTENT_MIN = 0.97
FIELD_MIN = 0.95
EXACT_MIN = 0.90
FORMAT_MAX_GRAMMAR = 0.0  # 문법 강제 도구
FORMAT_MAX_FREE = 0.01  # 문법 강제가 없는 도구
DANGER_MAX = 0.005
LATENCY_MAX_MS = 5000  # 학과 관리자 PC, 문장 1개 평균
```

- [ ] **Step 4: 통과**

Run: `cd ml && uv run pytest tests/test_records.py -q` → `5 passed`.
Run: `uv run ruff check . && uv run ruff format --check .` → 통과.

- [ ] **Step 5: CI job**

`.github/workflows/ci.yml` — `changes` job 의 `outputs:` 에 한 줄 추가:
```yaml
      ml: ${{ steps.filter.outputs.ml }}
```
`filters: |` 안에 추가:
```yaml
            ml:
              - 'ml/**'
              - 'assistant_proto/**'
              - '.github/workflows/ci.yml'
```
`modempi` job 뒤에 새 job:
```yaml
  # ===== ml: 관리자 AI 비서 모델 도구 (GPU·API 없이 — 생성기·다양화 검증·라벨·채점·릴리스 도우미) =====
  ml:
    needs: changes
    if: ${{ needs.changes.outputs.ml == 'true' }}
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ml
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: setup
        run: |
          pip install uv
          uv sync --frozen
      - name: lint
        run: uv run ruff check . && uv run ruff format --check .
      - name: test
        run: uv run pytest -q
```

- [ ] **Step 6: 커밋**

```bash
cd ml && uv lock && cd ..
git add ml/pyproject.toml ml/uv.lock ml/README.md ml/esc_ml/__init__.py ml/esc_ml/records.py \
  ml/esc_ml/gates.py ml/tests/__init__.py ml/tests/test_records.py
git commit -m "feat(ml): 뼈대 — uv 프로젝트, 예문·예측 레코드, 합격선 상수"
git add .github/workflows/ci.yml
git commit -m "chore(infra): CI ml job — 생성기·채점기 단위 테스트(GPU 없이)"
```

---

### Task 3: 템플릿 생성기 (선행: PR A 머지)

**Files:**
- Create: `ml/esc_ml/gen/__init__.py`, `ml/esc_ml/gen/values.py`, `ml/esc_ml/gen/templates.py`, `ml/esc_ml/gen/build.py`, `ml/esc_ml/gen/__main__.py`
- Test: `ml/tests/test_gen.py`

**Interfaces:**
- Consumes: `assistant_proto.FIRST_PREFIX`, `SCHEMA_VERSION`, `INTENTS`, `render_prefix`, `parse_form`, `canonical_json`, `rules.missing`·`rules.question`·`rules.state_items` (01 Task 3 — 서버와 같은 접두어); `esc_ml.records.Example`, `missing_spans`
- Produces: `esc_ml.gen.build.generate(n: int, seed: int) -> list[Example]`, `state_prefix(rng, base=None, missing=None) -> tuple[str, str, str]`, `intent_counts(rows) -> Counter`; `esc_ml.gen.templates.TEMPLATES`, `FILL_TEMPLATES`, `MORE_TEMPLATES`, `PLACEHOLDER`, `Tpl`; CLI `python -m esc_ml.gen --n --seed --out` → `<out>/train.jsonl`, `<out>/val.jsonl`

- [ ] **Step 1: 실패 테스트**

`ml/tests/test_gen.py`:
```python
from assistant_proto import FIRST_PREFIX, INTENTS, canonical_json, parse_form

from esc_ml.gen.build import generate
from esc_ml.gen.templates import FILL_TEMPLATES, MORE_TEMPLATES, PLACEHOLDER, TEMPLATES
from esc_ml.records import missing_spans

ROWS = generate(3000, seed=1)
ALL_TPLS = (*TEMPLATES, *MORE_TEMPLATES, *(t for ts in FILL_TEMPLATES.values() for t in ts))


def test_forms_follow_schema():
    for r in ROWS:
        parse_form(r.form)


def test_canonical_roundtrip():
    for r in ROWS[:300]:
        assert canonical_json(parse_form(canonical_json(r.form))) == canonical_json(r.form)


def test_spans_are_verbatim():
    bad = [(r.id, missing_spans(r.utterance, r.form)) for r in ROWS if missing_spans(r.utterance, r.form)]
    assert bad == []


def test_all_intents_covered():
    assert {r.form["intent"] for r in ROWS} == set(INTENTS)


def test_dialog_share():
    share = sum(r.form["intent"] in ("fill", "cancel", "unknown") for r in ROWS) / len(ROWS)
    assert 0.10 <= share <= 0.18


def test_val_templates_never_in_train():
    train = {r.template for r in ROWS if r.split == "train"}
    val = {r.template for r in ROWS if r.split == "val"}
    assert val and train.isdisjoint(val)
    assert all("/v" in t for t in val)


def test_deterministic():
    assert generate(50, seed=3) == generate(50, seed=3)
    assert generate(50, seed=3) != generate(50, seed=4)


def test_prefix_shape():
    for r in ROWS:
        assert r.prefix == FIRST_PREFIX or (
            r.prefix.startswith("상태: ") and r.prefix.endswith("관리자: ")
        )


def test_fill_prefix_matches_server_rules():
    # 이어지는 답의 접두어는 서버와 같은 rules 함수로 만든다 — 학습·운영 입력 모양이 같아야 한다
    import random

    from assistant_proto import rules
    from esc_ml.gen.build import FILL_BASE, state_prefix

    rng = random.Random(0)
    for base, (sec, fields) in FILL_BASE.items():
        for f in fields:
            prefix, _, missing = state_prefix(rng, base, f)
            q = prefix.split("\n")[1]
            assert missing == f
            assert q.startswith("질문: ")
            assert q.removeprefix("질문: ") in {
                rules.question(base, f"{sec}.{f}", t) for t in (None, "특강", "대여", "수업", "시험", "휴강", "빈강의실")
            }


def test_each_placeholder_once():
    for t in ALL_TPLS:
        names = PLACEHOLDER.findall(t.text)
        assert len(names) == len(set(names)), t.id


def test_every_intent_has_train_and_val_template():
    for intent in {t.intent for t in TEMPLATES}:
        splits = {t.split for t in TEMPLATES if t.intent == intent}
        assert splits == {"train", "val"}, intent
    for field, ts in FILL_TEMPLATES.items():
        assert {t.split for t in ts} == {"train", "val"}, field


def test_dialog_forms_shape():
    for r in ROWS:
        intent = r.form["intent"]
        if intent == "fill":
            assert r.form["target"] == {} and len(r.form["set"]) == 1
        if intent in ("cancel", "unknown"):
            assert r.form["target"] == {} and r.form["set"] == {}
```

Run: `cd ml && uv run pytest tests/test_gen.py -q` → FAIL (`ModuleNotFoundError: esc_ml.gen`).

- [ ] **Step 2: 가상 값**

`ml/esc_ml/gen/__init__.py`:
```python
"""학습·검증 예문 생성기 — 문장 틀 × 가상 값."""
```

`ml/esc_ml/gen/values.py`:
```python
"""가상 값 — 실제 학교·교수·학생 이름을 쓰지 않는다(공개 저장소에 올라간다)."""

from __future__ import annotations

import random

BUILDINGS = ("공학관", "인문관", "과학관", "미래관", "창의관")
SUBJECTS = (
    "자료구조", "알고리즘", "운영체제", "데이터베이스", "컴퓨터네트워크", "임베디드시스템",
    "회로이론", "디지털논리", "확률과통계", "선형대수", "캡스톤디자인", "웹프로그래밍",
    "인공지능개론", "기계학습", "신호및시스템", "전자기학", "마이크로프로세서",
)
SECTIONS = ("", "", "", " 01", " 02", " 101")
EVENTS = (
    "알고리즘 특강", "취업 설명회", "동아리 발표회", "AI 세미나", "졸업작품 심사",
    "학과 총회", "코딩 테스트 대비반", "보안 초청강연", "스터디 모임", "동아리 회의",
)
PROFESSORS = ("김하늘", "이도윤", "박서준", "최지우", "정민재", "강수아", "윤태오", "한예린", "서다은", "임주원")
REQUESTERS = ("홍길동", "김민수", "이서연", "박지훈", "20231234", "20240517")
REASONS = ("장비 점검", "학과 행사와 겹침", "시험 기간 사용 제한", "신청 시간이 너무 김", "청소 일정")

DATES = (
    "오늘", "내일", "모레",
    "이번 주 월요일", "이번 주 화요일", "이번 주 수요일", "이번 주 목요일", "이번 주 금요일",
    "다음 주 월요일", "다음 주 수요일", "다음 주 금요일", "다다음 주 화요일",
    "금요일", "목요일", "화",
    "12/3", "12월 3일", "12.3", "11/27", "12월 10일", "5일",
)
DATE_LISTS = ("화, 목", "화목", "월, 수, 금", "11/27, 12/4", "12/2, 12/9")
RANGES = ("12/15~19", "12/15~12/19", "15일부터 19일까지", "12월 15일부터 12월 19일까지", "10/20~24", "4/20~4/24")
WEEKDAY_SINGLE = ("월", "월요일", "화요일", "수", "목요일", "금", "매주 수요일")
WEEKDAY_MULTI = ("월수금", "화, 목")
SPANS = (
    "15시부터 18시까지", "3시부터 6시", "3~6시", "15:00-18:00", "오전 9시부터 12시까지",
    "9시부터 3시간", "오후 1시부터 3시까지", "13시~15시", "10시 반부터 12시",
    "오전 10시부터 오후 1시까지", "14:30-16:00",
)
STARTS = ("16시로", "3시 반으로", "오후 4시로", "10시로", "13시로")

TYPE_WORDS = {
    "수업": ("보강", "수업", "보충수업"),
    "시험": ("시험", "중간고사", "기말고사", "퀴즈"),
    "휴강": ("휴강",),
    "빈강의실": ("빈 강의실",),
    "특강": ("특강", "세미나", "초청강연", "특별강연"),
    "대여": ("대여", "대관", "사용 예약"),
}
# 날짜별 일정에서 고를 유형 — 빈강의실은 드물게
TYPE_LABELS_FOR_EVENTS = ("특강", "특강", "대여", "대여", "휴강", "수업", "시험", "빈강의실")
JOINERS = (", ", " · ", "랑 ", " 그리고 ")


def room_number(rng: random.Random) -> str:
    return f"{rng.randint(1, 12)}{rng.randint(1, 15):02d}"


def room_expr(rng: random.Random) -> str:
    n = room_number(rng)
    r = rng.random()
    if r < 0.45:
        return n
    if r < 0.75:
        return n + "호"
    b = rng.choice(BUILDINGS)
    return f"{b} {n}" if r < 0.9 else f"{b} {n}호"


def group_expr(rng: random.Random) -> str:
    floor = rng.randint(1, 12)
    if rng.random() < 0.5:
        return f"{floor}층 전체"
    a = rng.randint(1, 8)
    return f"{floor}{a:02d}~{floor}{a + rng.randint(2, 6):02d}"
```

- [ ] **Step 3: 문장 틀**

`ml/esc_ml/gen/templates.py`:
```python
"""문장 틀 — intent 마다 학습(train)·검증(val) 틀을 따로 둔다. 검증 틀은 학습에 쓰지 않는다.

자리표시: {s_X} = set 칸, {t_X} = target 칸, {x_X} = 문장에만 넣고 양식에는 넣지 않음.
X: rooms(강의실 1~3개) group(층·범위) when(날짜·목록) range(기간) days(요일) time(시각 구간)
   start(시작만 "16시로") type(유형 낱말) subject professor reason requester
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PLACEHOLDER = re.compile(r"\{([stx])_(\w+)\}")
FIELD_OF = {
    "rooms": "rooms", "group": "rooms",
    "when": "when", "range": "when", "days": "when",
    "time": "time", "start": "time",
    "type": "type", "subject": "subject", "professor": "professor",
    "reason": "reason", "requester": "requester",
}


@dataclass(frozen=True)
class Tpl:
    id: str
    split: str  # train | val
    intent: str
    text: str
    type_label: str | None = None  # 문장에 유형 낱말이 고정으로 들어 있을 때(예: "휴강")


T = Tpl
TEMPLATES: tuple[Tpl, ...] = (
    # A. 날짜별 일정
    T("event.add/01", "train", "event.add", "{s_rooms} {s_when} {s_time} {s_type} 예약해줘"),
    T("event.add/02", "train", "event.add", "{s_when} {s_time}에 {s_rooms}에서 {s_subject} {s_type} 잡아줘"),
    T("event.add/03", "train", "event.add", "{s_rooms} {s_when} {s_subject} 휴강 처리해줘", "휴강"),
    T("event.add/04", "train", "event.add", "{s_when} {s_rooms} {s_time} {s_subject} 보강 넣어줘", "수업"),
    T("event.add/05", "train", "event.add", "{s_subject} {s_type} {s_when} {s_time} {s_rooms}에 등록해줘"),
    T("event.add/06", "train", "event.add", "{s_rooms}에 {s_when} {s_time} {s_type} 하나 추가. 담당은 {s_professor}"),
    T("event.add/07", "train", "event.add", "{s_group} {s_when} 휴강", "휴강"),
    T("event.add/v1", "val", "event.add", "{s_rooms} {s_when} {s_time}에 {s_type} 일정 넣어 주실래요"),
    T("event.add/v2", "val", "event.add", "{s_when}에 {s_subject} {s_type} 있어서 {s_rooms} {s_time} 잡아 주세요"),
    T("event.change/01", "train", "event.change", "{t_rooms} {t_when} {t_subject} {s_start} 바꿔줘"),
    T("event.change/02", "train", "event.change", "{t_rooms} {t_when} {t_time} 일정 {s_when}로 옮겨줘"),
    T("event.change/03", "train", "event.change", "{t_when} {t_rooms} {t_subject} 이름 {s_subject}로 변경"),
    T("event.change/04", "train", "event.change", "{t_rooms} {t_when} {t_subject} 시간을 {s_time}로 수정"),
    T("event.change/v1", "val", "event.change", "{t_rooms} {t_when} {t_time}에 잡힌 거 {s_start} 해 주세요"),
    T("event.change/v2", "val", "event.change", "{t_when} {t_subject} 장소를 {s_rooms}로 바꿔"),
    T("event.remove/01", "train", "event.remove", "{t_rooms} {t_when} {t_subject} 취소해줘"),
    T("event.remove/02", "train", "event.remove", "{t_when} {t_time} {t_rooms} 일정 삭제"),
    T("event.remove/03", "train", "event.remove", "{t_rooms} {t_when} 잡혀 있는 {t_subject} 없애줘"),
    T("event.remove/v1", "val", "event.remove", "{t_rooms} {t_when}에 있는 {t_subject} 지워 주세요"),
    T("event.remove/v2", "val", "event.remove", "{t_when} {t_time}에 {t_rooms} 예약된 거 빼줘"),
    # B. 시험기간
    T("exam.add/01", "train", "exam.add", "{s_rooms} {s_range} 시험기간으로 설정해줘"),
    T("exam.add/02", "train", "exam.add", "{s_range} {s_rooms} 시험 기간 등록"),
    T("exam.add/03", "train", "exam.add", "{s_group} 시험기간 {s_range}"),
    T("exam.add/v1", "val", "exam.add", "{s_range} 동안 {s_rooms} 시험기간 잡아 주세요"),
    T("exam.change/01", "train", "exam.change", "{t_rooms} 시험기간 {s_range}로 바꿔줘"),
    T("exam.change/02", "train", "exam.change", "{t_rooms} {t_range} 시험기간을 {s_range}로 변경"),
    T("exam.change/v1", "val", "exam.change", "{t_rooms} 시험 기간 {s_range}로 수정 부탁해요"),
    T("exam.remove/01", "train", "exam.remove", "{t_rooms} 시험기간 없애줘"),
    T("exam.remove/02", "train", "exam.remove", "{t_rooms} {t_range} 시험기간 삭제"),
    T("exam.remove/v1", "val", "exam.remove", "{t_rooms}에 걸린 시험 기간 지워줘"),
    # C. 정규 시간표
    T("class.add/01", "train", "class.add", "{s_rooms} {s_days} {s_time} {s_subject} {s_professor} 교수님 수업 추가해줘"),
    T("class.add/02", "train", "class.add", "{s_days} {s_time} {s_rooms}에 {s_subject} 수업 넣어줘"),
    T("class.add/03", "train", "class.add", "정규 시간표에 {s_subject} 추가: {s_rooms} {s_days} {s_time}"),
    T("class.add/v1", "val", "class.add", "{s_rooms}에 {s_subject} 수업 {s_days} {s_time} 새로 등록해 주세요"),
    T("class.change/01", "train", "class.change", "{t_rooms} {t_days} {t_subject} 교수 {s_professor}으로 바꿔줘"),
    T("class.change/02", "train", "class.change", "{t_rooms} {t_days} {t_time} 수업 {s_start} 변경"),
    T("class.change/03", "train", "class.change", "{t_rooms} {t_days} {t_subject} 과목명 {s_subject}로 수정"),
    T("class.change/v1", "val", "class.change", "{t_days} {t_subject} 수업을 {s_rooms}로 옮겨 주세요"),
    T("class.remove/01", "train", "class.remove", "{t_rooms} {t_days} {t_subject} 수업 빼줘"),
    T("class.remove/02", "train", "class.remove", "{t_days} {t_time} {t_rooms} 정규 수업 삭제"),
    T("class.remove/v1", "val", "class.remove", "{t_rooms} 시간표에서 {t_days} {t_subject} 지워 주세요"),
    # D. 학생 신청
    T("request.approve/01", "train", "request.approve", "{t_rooms} {t_when} 신청 승인해줘"),
    T("request.approve/02", "train", "request.approve", "{t_requester} 신청 승인"),
    T("request.approve/03", "train", "request.approve", "{t_when} {t_rooms} {t_requester} 예약 신청 승인해 주세요"),
    T("request.approve/v1", "val", "request.approve", "{t_requester} 님이 낸 {t_rooms} 신청 허락해 줘"),
    T("request.reject/01", "train", "request.reject", "{t_rooms} {t_when} 신청 거절해줘. 사유는 {s_reason}"),
    T("request.reject/02", "train", "request.reject", "{t_requester} 신청 반려, 사유: {s_reason}"),
    T("request.reject/03", "train", "request.reject", "{t_rooms} 신청 거절"),
    T("request.reject/v1", "val", "request.reject", "{t_when} {t_rooms} 신청은 {s_reason} 때문에 안 돼요 거절해 주세요"),
    # E. 조회
    T("ask.free_rooms/01", "train", "ask.free_rooms", "{t_when} {t_time} 빈 강의실 있어?"),
    T("ask.free_rooms/02", "train", "ask.free_rooms", "{t_when} 비어 있는 강의실 알려줘"),
    T("ask.free_rooms/03", "train", "ask.free_rooms", "{t_when} {t_time}에 {t_group} 중 빈 곳 있어?"),
    T("ask.free_rooms/v1", "val", "ask.free_rooms", "{t_when} {t_time} 사용 가능한 강의실 찾아 주세요"),
    T("ask.schedule/01", "train", "ask.schedule", "{t_rooms} {t_when} 일정 보여줘"),
    T("ask.schedule/02", "train", "ask.schedule", "{t_rooms} 시간표 알려줘"),
    T("ask.schedule/v1", "val", "ask.schedule", "{t_rooms} {t_when}에 뭐 있어요?"),
    T("ask.requests/01", "train", "ask.requests", "대기 중인 신청 보여줘"),
    T("ask.requests/02", "train", "ask.requests", "{t_rooms} 승인 대기 목록"),
    T("ask.requests/03", "train", "ask.requests", "{t_when} 들어온 신청 있어?"),
    T("ask.requests/v1", "val", "ask.requests", "아직 처리 안 한 예약 신청 뭐 있지"),
    T("ask.node/01", "train", "ask.node", "{t_rooms} 노드 상태 어때?"),
    T("ask.node/02", "train", "ask.node", "{t_rooms} 배터리 몇 퍼센트야?"),
    T("ask.node/v1", "val", "ask.node", "{t_rooms} 문 앞 화면 잘 돌아가?"),
    # 대화
    T("cancel/01", "train", "cancel", "취소"),
    T("cancel/02", "train", "cancel", "그만할래"),
    T("cancel/03", "train", "cancel", "됐어 안 할래"),
    T("cancel/04", "train", "cancel", "아니 취소해"),
    T("cancel/05", "train", "cancel", "처음부터 다시 할게"),
    T("cancel/v1", "val", "cancel", "이거 안 할게요"),
    T("cancel/v2", "val", "cancel", "그만 둘게"),
    T("unknown/01", "train", "unknown", "점심 뭐 먹지"),
    T("unknown/02", "train", "unknown", "오늘 날씨 어때"),
    T("unknown/03", "train", "unknown", "지난달 가장 많이 빈 강의실 분석해줘"),
    T("unknown/04", "train", "unknown", "{x_rooms} 강의실 새로 만들어줘"),
    T("unknown/05", "train", "unknown", "{x_rooms} 노드 재부팅해줘"),
    T("unknown/06", "train", "unknown", "{x_rooms} 노드 등록해줘"),
    T("unknown/07", "train", "unknown", "고마워"),
    T("unknown/v1", "val", "unknown", "{x_rooms} 강의실 삭제해줘"),
    T("unknown/v2", "val", "unknown", "모든 학생한테 공지 보내줘"),
)

# 되물음에 대한 답 — 빠진 칸 하나를 채운다 (intent fill)
FILL_TEMPLATES: dict[str, tuple[Tpl, ...]] = {
    "subject": (
        T("fill.subject/01", "train", "fill", "{s_subject}"),
        T("fill.subject/02", "train", "fill", "{s_subject}요"),
        T("fill.subject/03", "train", "fill", "이름은 {s_subject}"),
        T("fill.subject/v1", "val", "fill", "{s_subject}로 해 주세요"),
    ),
    "time": (
        T("fill.time/01", "train", "fill", "{s_time}"),
        T("fill.time/02", "train", "fill", "{s_time}요"),
        T("fill.time/v1", "val", "fill", "{s_time}로 할게요"),
    ),
    "when": (
        T("fill.when/01", "train", "fill", "{s_when}"),
        T("fill.when/02", "train", "fill", "{s_when}이요"),
        T("fill.when/v1", "val", "fill", "{s_when}로요"),
    ),
    "rooms": (
        T("fill.rooms/01", "train", "fill", "{s_rooms}"),
        T("fill.rooms/02", "train", "fill", "{s_rooms}에서 할게"),
        T("fill.rooms/v1", "val", "fill", "{s_rooms}로 해 주세요"),
    ),
    "type": (
        T("fill.type/01", "train", "fill", "{s_type}"),
        T("fill.type/v1", "val", "fill", "{s_type} 일정이에요"),
    ),
    "professor": (
        T("fill.professor/01", "train", "fill", "{s_professor} 교수님"),
        T("fill.professor/v1", "val", "fill", "담당은 {s_professor}"),
    ),
    "reason": (
        T("fill.reason/01", "train", "fill", "{s_reason}"),
        T("fill.reason/v1", "val", "fill", "사유는 {s_reason}입니다"),
    ),
}
# 대화 중 강의실을 더하는 답 ("아 801도 같이") — 서버가 rooms 를 더한다
MORE_TEMPLATES: tuple[Tpl, ...] = (
    T("fill.more/01", "train", "fill", "아 {s_rooms}도 같이"),
    T("fill.more/02", "train", "fill", "{s_rooms}도 추가"),
    T("fill.more/v1", "val", "fill", "{s_rooms}도 추가해 주세요"),
)
```

- [ ] **Step 4: 생성기**

`ml/esc_ml/gen/build.py`:
```python
"""생성기 — 틀 × 가상 값 → Example. 정답 표현은 문장에 넣은 글자 그대로라 항상 맞다."""

from __future__ import annotations

import datetime as dt
import random
import re
from collections import Counter

from assistant_proto import FIRST_PREFIX, SCHEMA_VERSION, render_prefix, rules

from esc_ml.gen import values as V
from esc_ml.gen.templates import FIELD_OF, FILL_TEMPLATES, MORE_TEMPLATES, PLACEHOLDER, TEMPLATES, Tpl
from esc_ml.records import Example

KST = dt.timezone(dt.timedelta(hours=9))
VAL_SHARE = 0.06
DIALOG_SHARE = {"fill": 0.08, "cancel": 0.03, "unknown": 0.04}  # 합 15% (spec §8.2 10~15%)
MID_DIALOG_SHARE = 0.05  # 대화 중 전혀 다른 새 요청
MORE_SHARE = 0.15  # fill 중 "아 801도 같이"
TASK_INTENTS = tuple(sorted({t.intent for t in TEMPLATES} - {"cancel", "unknown"}))

# 서버(01 Task 9~10)가 실제로 되묻는 작업과 칸 — rules.missing 이 그 칸을 돌려주는 경우만 만든다.
# (섹션, 칸 목록). professor·request.* 는 서버가 묻지 않으므로 넣지 않는다.
FILL_BASE = {
    "event.add": ("set", ("rooms", "when", "type", "time", "subject")),
    "class.add": ("set", ("rooms", "when", "time", "subject")),
    "exam.add": ("set", ("rooms", "when")),
    "event.remove": ("target", ("rooms", "when", "time")),
    "class.remove": ("target", ("rooms", "when", "time")),
    "ask.free_rooms": ("target", ("when",)),
    "ask.schedule": ("target", ("rooms",)),
    "ask.node": ("target", ("rooms",)),
}
WHEN_KIND = {"exam.add": "range", "class.add": "days", "class.remove": "days"}  # when 자리를 이 종류로 뽑는다


def _sample(rng: random.Random, kind: str, intent: str) -> tuple[str, object]:
    """(문장에 넣을 글자, 양식 값). rooms 만 값이 목록이다."""
    if kind == "rooms":
        k = 1 if rng.random() < 0.75 else rng.choice((2, 3))
        rooms: list[str] = []
        while len(rooms) < k:
            r = V.room_expr(rng)
            if r not in rooms:
                rooms.append(r)
        return rng.choice(V.JOINERS).join(rooms), rooms
    if kind == "group":
        g = V.group_expr(rng)
        return g, [g]
    if kind == "type":
        label = rng.choice(V.TYPE_LABELS_FOR_EVENTS)
        return rng.choice(V.TYPE_WORDS[label]), label
    if kind == "when":
        pool = V.DATE_LISTS if intent == "event.add" and rng.random() < 0.15 else V.DATES
    elif kind == "range":
        pool = V.RANGES
    elif kind == "days":
        pool = V.WEEKDAY_MULTI if intent == "class.add" and rng.random() < 0.2 else V.WEEKDAY_SINGLE
    elif kind == "time":
        pool = V.SPANS
    elif kind == "start":
        pool = V.STARTS
    elif kind == "subject":
        if intent.startswith("class.") or rng.random() < 0.5:
            v = rng.choice(V.SUBJECTS) + rng.choice(V.SECTIONS)
            return v, v
        pool = V.EVENTS
    else:
        pool = {"professor": V.PROFESSORS, "reason": V.REASONS, "requester": V.REQUESTERS}[kind]
    v = rng.choice(pool)
    return v, v


def fill_template(
    rng: random.Random, tpl: Tpl, kind_override: dict[str, str] | None = None, ctx_intent: str | None = None
) -> tuple[str, dict]:
    form: dict = {"v": SCHEMA_VERSION, "intent": tpl.intent, "target": {}, "set": {}}
    intent_for_values = ctx_intent or tpl.intent

    def repl(m: re.Match[str]) -> str:
        side, name = m.group(1), m.group(2)
        kind = (kind_override or {}).get(name, name)
        text, value = _sample(rng, kind, intent_for_values)
        if side != "x":
            form["target" if side == "t" else "set"][FIELD_OF[name]] = value
        return text

    utterance = PLACEHOLDER.sub(repl, tpl.text)
    if tpl.type_label is not None:
        form["set"]["type"] = tpl.type_label
    return utterance, form


def state_prefix(
    rng: random.Random, base: str | None = None, missing: str | None = None
) -> tuple[str, str, str]:
    """서버가 되물을 때 주는 접두어와 **같은 함수**로 만든다 — rules.state_items·rules.question
    (01 작업지시서 Task 3). 칸 값은 서버처럼 문장 속 표현 그대로. 반환 (접두어, 작업, 빠진 칸)."""
    base = base or rng.choice(sorted(FILL_BASE))
    sec, fields = FILL_BASE[base]
    missing = missing or rng.choice(fields)
    filled: dict = {}
    for f in fields:
        if f == missing:
            continue
        kind = WHEN_KIND.get(base, "when") if f == "when" else f
        filled[f] = _sample(rng, kind, base)[1]
    if filled.get("type") == "휴강" and missing in ("time", "subject"):
        filled["type"] = "특강"  # 휴강이면 서버가 시각·이름을 묻지 않는다(rules.missing)
    target, set_ = (filled, {}) if sec == "target" else ({}, filled)
    slot = f"{sec}.{missing}"
    assert rules.missing(base, target, set_) == slot, (base, slot)  # 서버가 실제로 묻는 칸만
    items = rules.state_items(base, target, set_, slot)
    question = rules.question(base, slot, set_.get("type"))
    return render_prefix(base, items, question), base, missing


def _fill(rng: random.Random, split: str) -> tuple[str, str, dict, str]:
    prefix, base, missing = state_prefix(rng)
    if rng.random() < MORE_SHARE:
        tpl = rng.choice([t for t in MORE_TEMPLATES if t.split == split])
    else:
        tpl = rng.choice([t for t in FILL_TEMPLATES[missing] if t.split == split])
    override = {"when": WHEN_KIND[base]} if base in WHEN_KIND else None
    utterance, form = fill_template(rng, tpl, override, ctx_intent=base)
    return prefix, utterance, form, tpl.id


def _now(rng: random.Random) -> str:
    d = dt.date(2026, 9, 1) + dt.timedelta(days=rng.randrange(110))
    t = dt.datetime(d.year, d.month, d.day, rng.randint(9, 17), rng.choice((0, 15, 30, 45)), tzinfo=KST)
    return t.isoformat()


def _pick_intent(rng: random.Random) -> str:
    r = rng.random()
    acc = 0.0
    for name, share in DIALOG_SHARE.items():
        acc += share
        if r < acc:
            return name
    return rng.choice(TASK_INTENTS)


def generate(n: int, seed: int) -> list[Example]:
    rng = random.Random(seed)
    n_val = round(n * VAL_SHARE)
    out: list[Example] = []
    for split, count in (("train", n - n_val), ("val", n_val)):
        for i in range(count):
            intent = _pick_intent(rng)
            if intent == "fill":
                prefix, utterance, form, tid = _fill(rng, split)
            else:
                tpl = rng.choice([t for t in TEMPLATES if t.intent == intent and t.split == split])
                utterance, form = fill_template(rng, tpl)
                mid = 0.8 if intent == "cancel" else MID_DIALOG_SHARE
                prefix = state_prefix(rng)[0] if rng.random() < mid else FIRST_PREFIX
                tid = tpl.id
            out.append(
                Example(
                    id=f"g{seed}-{split[0]}{i:06d}",
                    split=split,
                    template=tid,
                    now=_now(rng),
                    prefix=prefix,
                    utterance=utterance,
                    form=form,
                )
            )
    return out


def intent_counts(rows: list[Example]) -> Counter:
    return Counter(r.form["intent"] for r in rows)
```

`ml/esc_ml/gen/__main__.py`:
```python
"""python -m esc_ml.gen --n 8000 --seed 7 --out data/gen"""

from __future__ import annotations

import argparse
from pathlib import Path

from esc_ml.gen.build import generate, intent_counts
from esc_ml.records import write_examples


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.gen", description="학습·검증 예문 생성")
    ap.add_argument("--n", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path("data/gen"))
    a = ap.parse_args(argv)
    rows = generate(a.n, a.seed)
    for split in ("train", "val"):
        part = [r for r in rows if r.split == split]
        write_examples(a.out / f"{split}.jsonl", part)
        print(f"{split}: {len(part)}건 → {a.out / f'{split}.jsonl'}")
    for intent, c in sorted(intent_counts(rows).items()):
        print(f"  {intent:16s} {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 통과**

Run: `cd ml && uv run pytest tests/test_gen.py -q` → `11 passed`.
`test_spans_are_verbatim` 이 실패하면 실패한 id 의 틀에서 자리표시 바로 뒤 글자가 값과 붙어 다른 뜻이 되는지 본다(예: `{s_start}로` 는 "16시로로"가 된다 — `start` 는 조사 없이 쓰는 틀에만).
Run: `uv run python -m esc_ml.gen --n 8000 --seed 7 --out data/gen` → `train: 7520건`, `val: 480건`, intent 18줄.

- [ ] **Step 6: 커밋**

```bash
git add ml/esc_ml/gen/__init__.py ml/esc_ml/gen/values.py ml/esc_ml/gen/templates.py \
  ml/esc_ml/gen/build.py ml/esc_ml/gen/__main__.py ml/tests/test_gen.py
git commit -m "feat(ml): 학습 예문 생성기 — intent 18개 문장 틀 × 가상 값, 학습·검증 틀 분리"
```

---

### Task 4: 다양화 — Claude 변형 + 해석기 검증 (선행: PR A 머지)

**Files:**
- Create: `ml/esc_ml/paraphrase.py`
- Test: `ml/tests/test_paraphrase.py`

**Interfaces:**
- Consumes: `assistant_proto.parse_form`, `FormError`; `assistant_proto.resolve.resolve_when`, `resolve_weekdays`, `resolve_time`, `normalize_room`; `esc_ml.records`
- Produces: `accept(ex: Example, variant: dict, idx: int) -> Example | None`, `call_claude(client, ex, k, model, effort, fallbacks) -> list[dict]`, `same_value(field, old, new, now, intent) -> bool`(Task 6 채점기와 같은 규칙), `run(argv=None, client=None) -> int`, CLI `python -m esc_ml.paraphrase`

claude-api 스킬 지침: 공식 `anthropic` SDK, 기본 모델 `claude-opus-5-5`(인자로 바꿈), 구조화 출력은 `output_config={"format": {"type": "json_schema", "schema": …}}`, Opus 5.5 는 `thinking` 을 보내지 않고 `output_config.effort` 로 조절(이 모델 기본 `medium` — 명시), 거절 대비 서버 측 fallbacks(`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`) 기본 켬(`--no-fallbacks` 로 끔 — Haiku 등 미지원 모델), `stop_reason` 을 먼저 확인.

- [ ] **Step 1: 실패 테스트**

`ml/tests/test_paraphrase.py`:
```python
import json
from types import SimpleNamespace

from assistant_proto import FIRST_PREFIX

from esc_ml import paraphrase as P
from esc_ml.records import Example, read_examples, write_examples

EX = Example(
    id="g1-t000001",
    split="train",
    template="event.add/01",
    now="2026-11-25T10:00:00+09:00",
    prefix=FIRST_PREFIX,
    utterance="803 금요일 15시부터 18시까지 특강 예약해줘",
    form={
        "v": 1,
        "intent": "event.add",
        "target": {},
        "set": {"rooms": ["803"], "when": "금요일", "time": "15시부터 18시까지", "type": "특강"},
    },
)
EX_SUBJ = Example(
    id="g1-t000002",
    split="train",
    template="event.add/02",
    now="2026-11-25T10:00:00+09:00",
    prefix=FIRST_PREFIX,
    utterance="금요일 3시부터 6시에 803에서 알고리즘 특강 특강 잡아줘",
    form={
        "v": 1,
        "intent": "event.add",
        "target": {},
        "set": {"rooms": ["803"], "when": "금요일", "time": "3시부터 6시", "subject": "알고리즘 특강", "type": "특강"},
    },
)


def variant(text, **set_):
    empty = {k: None for k in P.SPAN_FIELDS}
    return {"text": text, "target": dict(empty), "set": {**empty, **set_}}


class FakeMessages:
    def __init__(self, payload, stop="end_turn"):
        self.payload, self.stop, self.calls, self.kw = payload, stop, 0, None

    def create(self, **kw):
        self.calls += 1
        self.kw = kw
        block = SimpleNamespace(type="text", text=json.dumps(self.payload, ensure_ascii=False))
        return SimpleNamespace(stop_reason=self.stop, content=[block])


class FakeClient:
    def __init__(self, messages):
        self.messages = messages
        self.beta = SimpleNamespace(messages=messages)


GOOD = variant("803호 금요일 3시부터 6시 특강 잡아줘", rooms=["803호"], when="금요일", time="3시부터 6시")


def test_accepts_same_meaning():
    got = P.accept(EX, GOOD, idx=0)
    assert got is not None
    assert got.utterance == "803호 금요일 3시부터 6시 특강 잡아줘"
    assert got.form["set"]["time"] == "3시부터 6시" and got.form["set"]["rooms"] == ["803호"]
    assert got.form["set"]["type"] == "특강" and got.id == "g1-t000001-p0"
    assert got.template == "event.add/01+p"


def test_rejects_changed_time():
    v = variant("803 금요일 4시부터 6시 특강", rooms=["803"], when="금요일", time="4시부터 6시")
    assert P.accept(EX, v, idx=0) is None


def test_rejects_span_not_in_text():
    v = variant("803 금요일 오후 특강 잡아줘", rooms=["803"], when="금요일", time="3시부터 6시")
    assert P.accept(EX, v, idx=0) is None


def test_rejects_new_field():
    v = variant(
        "803 금요일 3시부터 6시 김하늘 특강",
        rooms=["803"], when="금요일", time="3시부터 6시", professor="김하늘",
    )
    assert P.accept(EX, v, idx=0) is None


def test_subject_spacing_ok_but_change_rejected():
    ok = variant(
        "금요일 3시부터 6시 803 알고리즘특강 잡아줘",
        rooms=["803"], when="금요일", time="3시부터 6시", subject="알고리즘특강",
    )
    assert P.accept(EX_SUBJ, ok, idx=1) is not None
    bad = variant(
        "금요일 3시부터 6시 803 AI 특강 잡아줘",
        rooms=["803"], when="금요일", time="3시부터 6시", subject="AI 특강",
    )
    assert P.accept(EX_SUBJ, bad, idx=1) is None


def test_call_claude_request_and_parse():
    fake = FakeMessages({"variants": [GOOD]})
    out = P.call_claude(FakeClient(fake), EX, k=3, model="claude-opus-5-5", effort="medium", fallbacks=True)
    assert out == [GOOD]
    kw = fake.kw
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["effort"] == "medium"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "803" in kw["messages"][0]["content"]


def test_refusal_returns_empty():
    fake = FakeMessages({"variants": [GOOD]}, stop="refusal")
    assert P.call_claude(FakeClient(fake), EX, 3, "claude-opus-5-5", "medium", True) == []


def test_run_without_yes_makes_no_calls(tmp_path, capsys):
    write_examples(tmp_path / "in.jsonl", [EX])
    fake = FakeMessages({"variants": [GOOD]})
    code = P.run(["--in", str(tmp_path / "in.jsonl"), "--out", str(tmp_path / "out.jsonl")], client=FakeClient(fake))
    assert code == 2 and fake.calls == 0
    assert "--yes" in capsys.readouterr().out


def test_run_with_yes_writes_accepted(tmp_path):
    write_examples(tmp_path / "in.jsonl", [EX])
    fake = FakeMessages({"variants": [GOOD, variant("엉뚱한 문장", rooms=["803"])]})
    code = P.run(
        ["--in", str(tmp_path / "in.jsonl"), "--out", str(tmp_path / "out.jsonl"), "--yes"],
        client=FakeClient(fake),
    )
    assert code == 0
    (got,) = read_examples(tmp_path / "out.jsonl")
    assert got.utterance == GOOD["text"]
```

Run: `cd ml && uv run pytest tests/test_paraphrase.py -q` → FAIL (`ImportError: esc_ml.paraphrase`).

- [ ] **Step 2: 구현**

`ml/esc_ml/paraphrase.py`:
```python
"""학습 문장 다양화 — Claude 로 표현만 바꾼 변형을 만들고, 해석기로 뜻이 같은 것만 남긴다.

가상 데이터만 보낸다. --yes 가 없으면 예상 호출 수·토큰·비용만 보이고 API 를 부르지 않는다(비용 승인).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from assistant_proto import FormError, parse_form
from assistant_proto.resolve import normalize_room, resolve_time, resolve_weekdays, resolve_when

from esc_ml.records import SPAN_FIELDS, Example, read_examples, write_examples

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# 2026-11 기준 1M 토큰당 USD (입력, 출력) — 예상 비용 표시용. 가격이 바뀌면 고친다
PRICE = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}

INSTRUCTION = """너는 대학 강의실 관리자가 AI 비서에게 하는 요청 문장의 변형을 만든다.
입력: 원래 문장과, 그 문장 속 칸 값(target·set — 강의실·날짜·시각·이름 등, 문장에 있는 글자 그대로).
할 일: 뜻과 정보는 그대로 두고 표현만 바꾼 변형 {k}개를 만든다.
- 섞을 것: 구어체, 존댓말/반말, 줄임말, 띄어쓰기 생략, 흔한 오타 한 개 정도, 어순 바꾸기.
- 날짜·시각·강의실·이름을 다른 값으로 바꾸지 않는다. "3시부터 6시"를 "15시~18시"처럼 같은 뜻의 다른 표현으로 바꾸는 것은 좋다.
- 원래 없던 정보(교수·사유 등)를 더하지 않는다.
- 각 변형의 target·set 에는 그 변형 문장 속에 실제로 쓰인 글자 그대로를 적는다. 원래 없던 칸은 null.
"""


def _fields_schema() -> dict:
    nullable_str = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    props = {k: dict(nullable_str) for k in SPAN_FIELDS}
    props["rooms"] = {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}
    return {"type": "object", "additionalProperties": False, "required": list(SPAN_FIELDS), "properties": props}


def variant_schema() -> dict:
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "target", "set"],
        "properties": {"text": {"type": "string"}, "target": _fields_schema(), "set": _fields_schema()},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["variants"],
        "properties": {"variants": {"type": "array", "items": item}},
    }


def request_payload(ex: Example) -> str:
    spans = {
        side: {k: v for k, v in ex.form[side].items() if k in SPAN_FIELDS} for side in ("target", "set")
    }
    return json.dumps({"문장": ex.utterance, "칸": spans}, ensure_ascii=False)


def call_claude(client, ex: Example, k: int, model: str, effort: str, fallbacks: bool) -> list[dict]:
    kw = dict(
        model=model,
        max_tokens=4096,
        system=INSTRUCTION.format(k=k),
        messages=[{"role": "user", "content": request_payload(ex)}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": variant_schema()}},
    )
    if fallbacks:
        resp = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kw)
    else:
        resp = client.messages.create(**kw)
    if resp.stop_reason != "end_turn":  # refusal·max_tokens 등 — 이 문장은 건너뛴다
        return []
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["variants"]


def _squash(s: str) -> str:
    return "".join(s.split())


def same_value(field: str, old, new, now: datetime, intent: str) -> bool:
    """두 표현이 같은 값인가 — 채점기(score.py)와 같은 규칙."""
    if field == "rooms":
        return sorted(normalize_room(x) for x in old) == sorted(normalize_room(x) for x in new)
    if field == "when":
        if intent.startswith("class."):
            a, b = resolve_weekdays(old), resolve_weekdays(new)
        else:
            a, b = resolve_when(old, now), resolve_when(new, now)
        return (a == b) if (a is not None or b is not None) else _squash(old) == _squash(new)
    if field == "time":
        a, b = resolve_time(old), resolve_time(new)
        return (a == b) if (a is not None or b is not None) else _squash(old) == _squash(new)
    return _squash(old) == _squash(new)


def accept(ex: Example, variant: dict, idx: int) -> Example | None:
    text = variant["text"].strip()
    if not text or text == ex.utterance:
        return None
    now = datetime.fromisoformat(ex.now)
    intent = ex.form["intent"]
    form = copy.deepcopy(ex.form)
    for side in ("target", "set"):
        orig, got = ex.form[side], variant[side]
        for f in SPAN_FIELDS:
            new = got.get(f)
            if f not in orig:
                if new:  # 원래 없던 칸이 생겼다
                    return None
                continue
            if not new:
                return None
            # 원래 값이 풀리지 않는 표현이면(예: "오후") 같은 글자일 때만 받는다
            if not same_value(f, orig[f], new, now, intent):
                return None
            for v in new if f == "rooms" else [new]:
                if v not in text:
                    return None
            form[side][f] = list(new) if f == "rooms" else new
    try:
        parse_form(form)
    except FormError:
        return None
    return replace(ex, id=f"{ex.id}-p{idx}", template=f"{ex.template}+p", utterance=text, form=form)


def estimate(n_calls: int, k: int, model: str) -> str:
    tin, tout = 700 * n_calls, (60 + 90 * k) * n_calls  # 지시문·입력 약 700, 변형 1개 약 90 토큰
    pin, pout = PRICE.get(model, (0.0, 0.0))
    usd = tin / 1e6 * pin + tout / 1e6 * pout
    return f"호출 {n_calls}회 · 입력 약 {tin:,} · 출력 약 {tout:,} 토큰 · 예상 약 ${usd:,.2f} ({model})"


def make_client():
    import anthropic  # 선택 설치 (uv run --extra paraphrase)

    return anthropic.Anthropic()


def run(argv: list[str] | None = None, client=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.paraphrase", description="학습 문장 다양화")
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N 문장만 (0 = 전부)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default="medium", choices=("low", "medium", "high"))
    ap.add_argument("--no-fallbacks", action="store_true", help="서버 측 fallbacks 를 지원하지 않는 모델")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--yes", action="store_true", help="비용 승인 — 없으면 예상치만 출력")
    a = ap.parse_args(argv)

    rows = [r for r in read_examples(a.inp) if r.split in ("train", "val")]
    if a.limit:
        rows = rows[: a.limit]
    print(estimate(len(rows), a.variants, a.model))
    if not a.yes:
        print("API 를 부르지 않았습니다. 승인 후 --yes 를 붙여 다시 실행하세요.")
        return 2

    client = client or make_client()

    def work(ex: Example) -> tuple[list[Example], int]:
        try:
            vs = call_claude(client, ex, a.variants, a.model, a.effort, not a.no_fallbacks)
        except Exception as e:  # 한 문장 실패가 전체를 멈추지 않게 — 건수로 보고
            print(f"{ex.id}: {type(e).__name__}", file=sys.stderr)
            return [], 0
        return [x for i, v in enumerate(vs) if (x := accept(ex, v, i)) is not None], len(vs)

    kept: list[Example] = []
    asked = 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for got, n in pool.map(work, rows):
            kept += got
            asked += n
    write_examples(a.out, kept)
    print(f"변형 {asked}개 중 {len(kept)}개 남김 → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
```

- [ ] **Step 3: 통과**

Run: `cd ml && uv run pytest tests/test_paraphrase.py -q` → `9 passed`.
`test_accepts_same_meaning` 이 실패하면 `resolve_time("3시부터 6시") == resolve_time("15시부터 18시까지")` 를 먼저 확인한다 — 부록 §3 규칙(오전·오후 없는 1~8시 = 13~20시)대로면 같아야 한다. 다르면 이 Task 가 아니라 `assistant_proto` 쪽 이슈로 cw 에게 올린다.

- [ ] **Step 4: 비용 승인 → 실행 → HF 데이터 저장소**

```bash
cd ml
uv run --extra paraphrase python -m esc_ml.paraphrase --in data/gen/train.jsonl --out data/para/train.jsonl --variants 3 --limit 3000
```
출력된 예상 비용 줄을 cw 에게 보내 승인받는다. 승인 후:
```bash
export ANTHROPIC_API_KEY=…   # 커밋 금지, 셸에서만
uv run --extra paraphrase python -m esc_ml.paraphrase --in data/gen/train.jsonl --out data/para/train.jsonl --variants 3 --limit 3000 --yes
uv run --extra paraphrase python -m esc_ml.paraphrase --in data/gen/val.jsonl --out data/para/val.jsonl --variants 2 --yes
```
Expected: `변형 N개 중 M개 남김`. 남김 비율이 50% 미만이면 거절 사유를 샘플 20개로 확인한다 — 대부분 "해석기가 못 푸는 구어 표현(금욜·낼·담주)"이면 버리지 말고 cw 에게 해석기 보강 이슈로 올린다(부록 변경 제안).
데이터 저장소 업로드는 Task 11 의 `release.py upload-data` 로 한다(Kaggle 학습이 여기서 받는다).

- [ ] **Step 5: 커밋**

```bash
git add ml/esc_ml/paraphrase.py ml/tests/test_paraphrase.py
git commit -m "feat(ml): 학습 문장 다양화 — Claude 구조화 출력 + 해석기로 뜻이 같은 변형만 남김, --yes 비용 승인"
```

---

### Task 5: 사람 시험 세트 — 수집 양식·라벨링·겹침 검사 (선행: PR A 머지)

**Files:**
- Create: `ml/esc_ml/label.py`, `ml/esc_ml/overlap.py`, `ml/data/human_template.csv`
- Create (수집 후): `ml/data/test_human.jsonl`
- Test: `ml/tests/test_label.py`, `ml/tests/test_overlap.py`

**Interfaces:**
- Consumes: `assistant_proto.FIRST_PREFIX`, `FIELD_ORDER`, `SCHEMA_VERSION`, `canonical_json`, `parse_form`, `FormError`, `render_prefix`; `esc_ml.records`
- Produces: `label.parse_kv(line) -> dict`, `label.parse_items(text) -> list[tuple[str, str | None]]`, `label.row_prefix(row) -> str`, `label.label_row(row, ask, say) -> Example`; `overlap.near_duplicates(tests, trains, threshold=0.8, min_len=8) -> list[tuple[str, str, float]]`; CLI `python -m esc_ml.label`, `python -m esc_ml.overlap`

수집 규칙:
- 대상: 팀원, 조교, 학과 사무실 직원. 1인 30~60문장, 총 약 300.
- 실제로 쓸 법한 요청을 **자유롭게** 쓰되 intent 18개가 고루 나오도록 수집 시 "이런 일도 써 주세요" 목록(spec §1 A~F)을 보여 준다. 되물음에 대한 답(이어지는 턴)도 40문장 이상(앞 상태를 우리가 정해 주고 답만 받는다).
- **가상화**: 실제 교수·학생 이름, 실제 학번이 들어가면 커밋 전에 `esc_ml/gen/values.py` 의 가상 이름으로 바꾼다. 원본 CSV 는 `ml/data/raw/`(무시됨)에만 둔다.

- [ ] **Step 1: 수집 양식**

`ml/data/human_template.csv` (UTF-8 BOM, 엑셀·구글 시트로 열어 채운다):
```csv
id,now,ctx_intent,ctx_items,ctx_question,utterance,writer,memo
h001,2026-12-01 10:00,,,,803호 이번주 금요일 3시부터 6시까지 세미나 잡아줘,A,
h002,2026-12-01 10:00,event.add,강의실=803; 날짜=12/5(금); 시각=15:00~18:00; 유형=특강; 이름=?,특강 이름은 무엇인가요?,알고리즘 특강이요,A,이어지는 턴
```
열: `id`(고유), `now`(쓴 시각 — 상대 날짜 기준, `YYYY-MM-DD HH:MM` KST), `ctx_*`(이어지는 턴만: 앞 상태의 작업·칸·질문 — `칸=값` 을 `;` 로, 빈 칸은 `?`), `utterance`, `writer`(익명 코드), `memo`.

- [ ] **Step 2: 실패 테스트**

`ml/tests/test_label.py`:
```python
import pytest
from assistant_proto import FIRST_PREFIX, render_prefix

from esc_ml.label import label_row, parse_items, parse_kv, row_prefix

ROW = {
    "id": "h001",
    "now": "2026-12-01 10:00",
    "ctx_intent": "",
    "ctx_items": "",
    "ctx_question": "",
    "utterance": "803호 이번주 금요일 3시부터 6시까지 세미나 잡아줘",
}


def scripted(answers):
    it = iter(answers)
    said = []
    return (lambda prompt: next(it)), said.append, said


def test_parse_kv():
    assert parse_kv("rooms=803, 801; when=이번 주 금요일; type=특강") == {
        "rooms": ["803", "801"],
        "when": "이번 주 금요일",
        "type": "특강",
    }
    assert parse_kv("  ") == {}
    with pytest.raises(ValueError):
        parse_kv("room=803")
    with pytest.raises(ValueError):
        parse_kv("rooms 803")


def test_parse_items_and_prefix():
    items = parse_items("강의실=803; 이름=?")
    assert items == [("강의실", "803"), ("이름", None)]
    row = dict(ROW, ctx_intent="event.add", ctx_items="강의실=803; 이름=?", ctx_question="이름은?")
    assert row_prefix(row) == render_prefix("event.add", items, "이름은?")
    assert row_prefix(ROW) == FIRST_PREFIX


def test_label_row_happy_path():
    ask, say, said = scripted(
        ["event.add", "", "rooms=803호; when=이번주 금요일; time=3시부터 6시까지; type=특강", "y"]
    )
    ex = label_row(ROW, ask, say)
    assert ex.id == "h-h001" and ex.split == "test" and ex.template == "human"
    assert ex.now == "2026-12-01T10:00:00+09:00"
    assert ex.form["set"]["rooms"] == ["803호"] and ex.form["set"]["type"] == "특강"
    assert any('"intent":"event.add"' in s for s in said)


def test_label_row_retries_on_bad_input():
    ask, say, said = scripted(
        ["event.ad", "", "", "event.add", "", "rooms=803호; type=특강", "y"]
    )
    ex = label_row(ROW, ask, say)
    assert ex.form["intent"] == "event.add"
    assert any(s.startswith("다시:") for s in said)


def test_label_row_warns_missing_span():
    ask, say, said = scripted(["event.add", "", "rooms=901", "y"])
    label_row(ROW, ask, say)
    assert any("문장에 그대로 없는 값" in s for s in said)
```

`ml/tests/test_overlap.py`:
```python
from assistant_proto import FIRST_PREFIX

from esc_ml.overlap import near_duplicates
from esc_ml.records import Example

FORM = {"v": 1, "intent": "cancel", "target": {}, "set": {}}


def ex(i, text):
    return Example(i, "test", "human", "2026-12-01T10:00:00+09:00", FIRST_PREFIX, text, FORM)


def test_exact_after_normalizing_is_flagged():
    got = near_duplicates([ex("a", "803호 금요일 세미나 잡아줘!")], [ex("b", "803호금요일 세미나잡아줘")])
    assert got == [("a", "b", 1.0)]


def test_short_phrases_are_exempt():
    assert near_duplicates([ex("a", "취소")], [ex("b", "취소")]) == []


def test_different_sentences_pass():
    got = near_duplicates(
        [ex("a", "공학관 803 다음 주 화요일 자료구조 휴강")],
        [ex("b", "801 시험기간 12/15~19 등록해줘")],
    )
    assert got == []
```

Run: `cd ml && uv run pytest tests/test_label.py tests/test_overlap.py -q` → FAIL (모듈 없음).

- [ ] **Step 3: 구현**

`ml/esc_ml/label.py`:
```python
"""사람 시험 문장 라벨링 — 수집 CSV → test_human.jsonl. 문장마다 intent 와 칸을 입력받아 규격 검사.

입력 모양: 'rooms=803, 801; when=이번 주 금요일; type=특강' (rooms 만 쉼표로 여러 개)
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from assistant_proto import (
    FIELD_ORDER,
    FIRST_PREFIX,
    SCHEMA_VERSION,
    FormError,
    canonical_json,
    parse_form,
    render_prefix,
)

from esc_ml.records import Example, missing_spans, read_examples, write_examples


def parse_kv(line: str) -> dict:
    out: dict = {}
    for part in line.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"'칸=값' 모양이 아님: {part}")
        k, v = (s.strip() for s in part.split("=", 1))
        if k not in FIELD_ORDER:
            raise ValueError(f"모르는 칸: {k}")
        out[k] = [x.strip() for x in v.split(",") if x.strip()] if k == "rooms" else v
    return out


def parse_items(text: str) -> list[tuple[str, str | None]]:
    items = []
    for part in text.split(";"):
        part = part.strip()
        if part:
            k, v = (s.strip() for s in part.split("=", 1))
            items.append((k, None if v == "?" else v))
    return items


def row_prefix(row: dict) -> str:
    if not (row.get("ctx_intent") or "").strip():
        return FIRST_PREFIX
    return render_prefix(row["ctx_intent"].strip(), parse_items(row["ctx_items"]), row["ctx_question"].strip())


def _now(text: str) -> str:
    day, hm = text.strip().split()
    return f"{day}T{hm}:00+09:00"


def label_row(row: dict, ask, say) -> Example:
    prefix = row_prefix(row)
    say(f"\n[{row['id']}]\n{prefix}{row['utterance']}")
    while True:
        intent = ask("intent> ").strip()
        try:
            target = parse_kv(ask("target> "))
            set_ = parse_kv(ask("set> "))
            form = {"v": SCHEMA_VERSION, "intent": intent, "target": target, "set": set_}
            parse_form(form)
        except (ValueError, FormError) as e:
            say(f"다시: {e}")
            continue
        miss = missing_spans(row["utterance"], form)
        if miss:
            say(f"경고 — 문장에 그대로 없는 값: {miss}")
        say(canonical_json(form))
        if ask("저장? [Y/n]> ").strip().lower() in ("", "y"):
            return Example(
                id=f"h-{row['id']}",
                split="test",
                template="human",
                now=_now(row["now"]),
                prefix=prefix,
                utterance=row["utterance"],
                form=form,
            )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.label", description="사람 시험 문장 라벨링")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/test_human.jsonl"))
    a = ap.parse_args(argv)
    done = read_examples(a.out) if a.out.exists() else []
    seen = {e.id for e in done}
    with a.csv.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if f"h-{r['id']}" not in seen]
    print(f"라벨할 문장 {len(rows)}개 (이미 {len(done)}개). 중간에 Ctrl+C 로 멈춰도 저장된 것까지 남는다.")
    for r in rows:
        done.append(label_row(r, input, print))
        write_examples(a.out, done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`ml/esc_ml/overlap.py`:
```python
"""시험 문장 ↔ 학습 문장 겹침 검사 — 같거나 거의 같은 문장이 학습에 있으면 시험이 의미 없다."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from esc_ml.records import Example, read_examples

_STRIP = re.compile(r"[\s\W_]+")


def norm(s: str) -> str:
    return _STRIP.sub("", s.lower())


def grams(s: str, n: int = 4) -> set[str]:
    t = norm(s)
    return {t[i : i + n] for i in range(max(1, len(t) - n + 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def near_duplicates(
    tests: list[Example], trains: list[Example], threshold: float = 0.8, min_len: int = 8
) -> list[tuple[str, str, float]]:
    """(시험 id, 학습 id, 유사도). 정규화 길이가 min_len 미만인 짧은 말("취소")은 겹쳐도 어쩔 수 없어 뺀다."""
    exact = {norm(t.utterance): t.id for t in trains}
    train_grams = [(t.id, grams(t.utterance)) for t in trains]
    out = []
    for e in tests:
        n = norm(e.utterance)
        if len(n) < min_len:
            continue
        if n in exact:
            out.append((e.id, exact[n], 1.0))
            continue
        g = grams(e.utterance)
        best = max(((tid, jaccard(g, tg)) for tid, tg in train_grams), key=lambda x: x[1], default=None)
        if best and best[1] >= threshold:
            out.append((e.id, best[0], round(best[1], 3)))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.overlap", description="시험 ↔ 학습 겹침 검사")
    ap.add_argument("--test", type=Path, nargs="+", required=True)
    ap.add_argument("--train", type=Path, nargs="+", required=True)
    a = ap.parse_args(argv)
    tests = [e for p in a.test for e in read_examples(p)]
    trains = [e for p in a.train for e in read_examples(p)]
    hits = near_duplicates(tests, trains)
    for h in hits:
        print(*h, sep="\t")
    print(f"겹침 {len(hits)}건 / 시험 {len(tests)}문장")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과**

Run: `cd ml && uv run pytest tests/test_label.py tests/test_overlap.py -q` → `8 passed`.

- [ ] **Step 5: 수집 → 라벨 → 겹침 검사**

```bash
cd ml
# 수집 시트를 CSV(UTF-8)로 내려받아 data/raw/human.csv 에 둔다 (커밋 안 됨)
uv run python -m esc_ml.label --csv data/raw/human.csv --out data/test_human.jsonl
uv run python -m esc_ml.overlap --test data/test_human.jsonl --train data/gen/train.jsonl data/para/train.jsonl
```
Expected: `겹침 0건 / 시험 3xx문장`, 종료 코드 0. 겹침이 있으면 **시험 문장을 지우지 말고** 그 문장을 만든 생성 틀(`template`)·다양화 결과를 학습 데이터에서 빼고 다시 생성한다.
커밋 전: `data/test_human.jsonl` 을 훑어 실명·실제 학번이 없는지 확인하고, 있으면 가상 이름으로 바꾼다.

- [ ] **Step 6: 커밋**

```bash
git add ml/esc_ml/label.py ml/esc_ml/overlap.py ml/data/human_template.csv \
  ml/tests/test_label.py ml/tests/test_overlap.py
git commit -m "feat(ml): 사람 시험 세트 — 수집 양식, 라벨링 CLI(규격 검사), 학습 겹침 검사"
git add ml/data/test_human.jsonl
git commit -m "feat(ml): 사람 시험 문장 N개 (가상화)"
```
(두 번째 커밋 메시지의 N 은 실제 개수로 쓴다.)

---

### Task 6: 채점기 (선행: PR A 머지)

**Files:**
- Create: `ml/esc_ml/score.py`
- Test: `ml/tests/test_score.py`

**Interfaces:**
- Consumes: `assistant_proto.parse_form`, `form_to_dict`, `canonical_json`, `FormError`; `esc_ml.paraphrase.same_value`; `esc_ml.records`; `esc_ml.gates`
- Produces: `Row`, `Summary` dataclass, `score_one(ex, pred) -> Row`, `summarize(rows) -> Summary`, `gate_results(s, grammar, require_latency=False) -> list[Gate]`, `render_report(title, s, rows, gates, examples, preds, config=None) -> str`; CLI `python -m esc_ml.score --data … [--vectors …] --pred … --title … --grammar/--no-grammar [--require-latency] [--config …] --out … [--json …]` — 종료 코드 0 = 합격선 모두 통과

채점 규칙:
- 형식: 출력 앞뒤 공백만 허용하고 `parse_form` 이 받아야 통과. 코드블록(```)으로 감싸도 **형식 오류**.
- intent 정확도 = intent 일치 / 전체(형식 오류는 틀림).
- 칸 정확도 = 맞은 칸 / (정답 칸 ∪ 예측 칸). 칸 = (target|set, 이름). 값 비교는 `same_value`(rooms 정규화·정렬, when/time 해석기로 푼 값, 그 외 공백 무시). 형식 오류 문장은 정답 칸 수만큼 틀림.
- 양식 전체 일치 = intent 일치 + 모든 칸 맞음.
- 위험 오류율 = (정답이 `*.add`·`*.change`·`request.approve` 인데 예측이 `*.remove`·`request.reject`) / 정답이 그런 문장 수.
- 응답 시간 = 예측의 `latency_ms` 평균(없으면 "—", `--require-latency` 면 불합격).

- [ ] **Step 1: 실패 테스트**

`ml/tests/test_score.py`:
```python
from assistant_proto import FIRST_PREFIX, canonical_json

from esc_ml.records import Example, Prediction
from esc_ml.score import gate_results, render_report, score_one, summarize

NOW = "2026-11-25T10:00:00+09:00"


def ex(i, form):
    return Example(i, "test", "human", NOW, FIRST_PREFIX, "문장", form)


ADD = {"v": 1, "intent": "event.add", "target": {}, "set": {"rooms": ["803"], "time": "15시부터 18시까지", "type": "특강"}}


def pred(i, form_or_text, ms=None):
    text = form_or_text if isinstance(form_or_text, str) else canonical_json(form_or_text)
    return Prediction(i, text, ms)


def test_exact_match():
    r = score_one(ex("a", ADD), pred("a", ADD))
    assert r.format_ok and r.exact and r.fields_ok == r.fields_total == 3


def test_equivalent_expressions_count_as_correct():
    p = {**ADD, "set": {"rooms": ["803호"], "time": "3~6시", "type": "특강"}}
    r = score_one(ex("a", ADD), pred("a", p))
    assert r.exact and r.fields_ok == 3


def test_extra_field_breaks_exact():
    p = {**ADD, "set": {**ADD["set"], "professor": "김하늘"}}
    r = score_one(ex("a", ADD), pred("a", p))
    assert not r.exact and r.fields_total == 4 and r.fields_ok == 3


def test_format_error():
    for text in ("```json\n{}\n```", '{"v":1,"intent":"event.added","target":{},"set":{}}', ""):
        r = score_one(ex("a", ADD), pred("a", text))
        assert not r.format_ok and not r.exact and r.fields_ok == 0 and r.fields_total == 3


def test_missing_prediction_is_format_error():
    r = score_one(ex("a", ADD), None)
    assert not r.format_ok and r.error == "예측 없음"


def test_dangerous_and_summary():
    rm = {"v": 1, "intent": "event.remove", "target": {"rooms": ["803"]}, "set": {}}
    rows = [score_one(ex("a", ADD), pred("a", rm, 1000)), score_one(ex("b", ADD), pred("b", ADD, 3000))]
    s = summarize(rows)
    assert s.n == 2 and s.intent_acc == 0.5 and s.danger_rate == 0.5
    assert s.latency_mean_ms == 2000 and s.format_err == 0.0


def test_gates_pass_and_latency_na():
    rows = [score_one(ex(str(i), ADD), pred(str(i), ADD)) for i in range(10)]
    s = summarize(rows)
    gates = gate_results(s, grammar=True)
    assert all(g.passed for g in gates if g.passed is not None)
    lat = next(g for g in gates if g.name.startswith("응답 시간"))
    assert lat.passed is None
    lat_req = next(g for g in gate_results(s, grammar=True, require_latency=True) if g.name.startswith("응답 시간"))
    assert lat_req.passed is False


def test_report_renders():
    rows = [score_one(ex("a", ADD), pred("a", "깨진 출력"))]
    s = summarize(rows)
    md = render_report("시험", s, rows, gate_results(s, grammar=False), {"a": ex("a", ADD)}, {"a": pred("a", "깨진 출력")})
    assert "# 시험" in md and "합격선" in md and "깨진 출력" in md and "event.add" in md
```

Run: `cd ml && uv run pytest tests/test_score.py -q` → FAIL.

- [ ] **Step 2: 구현**

`ml/esc_ml/score.py`:
```python
"""채점기 — HF 예측·브라우저 하네스 예측을 같은 규칙으로 채점하고 보고서를 만든다 (spec §8.3)."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from assistant_proto import FormError, canonical_json, form_to_dict, parse_form

from esc_ml import gates as G
from esc_ml.paraphrase import same_value
from esc_ml.records import Example, Prediction, load_vectors, read_examples, read_predictions


@dataclass(frozen=True)
class Row:
    id: str
    intent_gold: str
    intent_pred: str | None
    format_ok: bool
    exact: bool
    fields_ok: int
    fields_total: int
    dangerous: bool
    latency_ms: float | None
    error: str = ""


@dataclass(frozen=True)
class Summary:
    n: int
    intent_acc: float
    field_acc: float
    exact_acc: float
    format_err: float
    danger_rate: float
    latency_mean_ms: float | None
    latency_p90_ms: float | None


@dataclass(frozen=True)
class Gate:
    name: str
    value: str
    threshold: str
    passed: bool | None  # None = 해당 없음


def _items(form: dict) -> dict[tuple[str, str], object]:
    return {(side, k): v for side in ("target", "set") for k, v in form.get(side, {}).items()}


def _is_write(intent: str) -> bool:
    return intent.endswith((".add", ".change")) or intent == "request.approve"


def _is_destructive(intent: str) -> bool:
    return intent.endswith(".remove") or intent == "request.reject"


def score_one(ex: Example, pred: Prediction | None) -> Row:
    gold = _items(ex.form)
    gi = ex.form["intent"]
    lat = pred.latency_ms if pred else None
    if pred is None:
        return Row(ex.id, gi, None, False, False, 0, len(gold), False, None, "예측 없음")
    try:
        pd = form_to_dict(parse_form(pred.text.strip()))
    except (FormError, ValueError) as e:
        return Row(ex.id, gi, None, False, False, 0, len(gold), False, lat, f"형식: {e}")
    now = datetime.fromisoformat(ex.now)
    got = _items(pd)
    keys = set(gold) | set(got)
    ok = sum(
        1 for k in keys if k in gold and k in got and same_value(k[1], gold[k], got[k], now, gi)
    )
    pi = pd["intent"]
    exact = pi == gi and ok == len(keys)
    return Row(ex.id, gi, pi, True, exact, ok, len(keys), _is_write(gi) and _is_destructive(pi), lat)


def summarize(rows: list[Row]) -> Summary:
    n = len(rows)
    writes = [r for r in rows if _is_write(r.intent_gold)]
    lats = sorted(r.latency_ms for r in rows if r.latency_ms is not None)
    total = sum(r.fields_total for r in rows)
    return Summary(
        n=n,
        intent_acc=sum(r.intent_pred == r.intent_gold for r in rows) / n,
        field_acc=sum(r.fields_ok for r in rows) / total if total else 1.0,
        exact_acc=sum(r.exact for r in rows) / n,
        format_err=sum(not r.format_ok for r in rows) / n,
        danger_rate=sum(r.dangerous for r in writes) / len(writes) if writes else 0.0,
        latency_mean_ms=sum(lats) / len(lats) if lats else None,
        latency_p90_ms=lats[max(0, math.ceil(0.9 * len(lats)) - 1)] if lats else None,
    )


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def gate_results(s: Summary, grammar: bool, require_latency: bool = False) -> list[Gate]:
    fmax = G.FORMAT_MAX_GRAMMAR if grammar else G.FORMAT_MAX_FREE
    out = [
        Gate("intent 정확도", _pct(s.intent_acc), f"≥ {_pct(G.INTENT_MIN)}", s.intent_acc >= G.INTENT_MIN),
        Gate("칸 정확도", _pct(s.field_acc), f"≥ {_pct(G.FIELD_MIN)}", s.field_acc >= G.FIELD_MIN),
        Gate("양식 전체 일치", _pct(s.exact_acc), f"≥ {_pct(G.EXACT_MIN)}", s.exact_acc >= G.EXACT_MIN),
        Gate(
            f"형식 오류 ({'문법 강제' if grammar else '강제 없음'})",
            _pct(s.format_err),
            f"≤ {_pct(fmax)}",
            s.format_err <= fmax,
        ),
        Gate("위험 오류", _pct(s.danger_rate), f"≤ {_pct(G.DANGER_MAX)}", s.danger_rate <= G.DANGER_MAX),
    ]
    if s.latency_mean_ms is None:
        out.append(Gate("응답 시간 평균", "—", f"≤ {G.LATENCY_MAX_MS} ms", False if require_latency else None))
    else:
        out.append(
            Gate(
                "응답 시간 평균",
                f"{s.latency_mean_ms:.0f} ms (p90 {s.latency_p90_ms:.0f})",
                f"≤ {G.LATENCY_MAX_MS} ms",
                s.latency_mean_ms <= G.LATENCY_MAX_MS,
            )
        )
    return out


def render_report(
    title: str,
    s: Summary,
    rows: list[Row],
    gates: list[Gate],
    examples: dict[str, Example],
    preds: dict[str, Prediction],
    config: dict | None = None,
) -> str:
    mark = {True: "✅", False: "❌", None: "—"}
    lines = [f"# {title}", "", f"- 문장 수: {s.n}", "", "## 합격선", "", "| 지표 | 값 | 합격선 | 판정 |", "|---|---|---|---|"]
    lines += [f"| {g.name} | {g.value} | {g.threshold} | {mark[g.passed]} |" for g in gates]
    overall = all(g.passed is not False for g in gates)
    lines += ["", f"**종합: {'합격' if overall else '불합격'}**", ""]
    if config:
        lines += ["## 설정", "", "```json", json.dumps(config, ensure_ascii=False, indent=1), "```", ""]
    per: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        per[r.intent_gold].append(r)
    lines += ["## intent 별", "", "| intent | n | intent 정확도 | 전체 일치 |", "|---|---|---|---|"]
    for intent in sorted(per):
        rs = per[intent]
        ia = sum(r.intent_pred == r.intent_gold for r in rs) / len(rs)
        ea = sum(r.exact for r in rs) / len(rs)
        lines.append(f"| {intent} | {len(rs)} | {_pct(ia)} | {_pct(ea)} |")
    fails = [r for r in rows if not r.exact][:30]
    lines += ["", f"## 틀린 문장 (앞 {len(fails)}개)", ""]
    for r in fails:
        e = examples[r.id]
        p = preds.get(r.id)
        lines += [
            f"- `{r.id}` {r.error}",
            f"  - 입력: `{e.user_text()!r}`",
            f"  - 정답: `{canonical_json(e.form)}`",
            f"  - 출력: `{p.text if p else '(없음)'}`",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.score", description="채점·보고서")
    ap.add_argument("--data", type=Path, nargs="*", default=[])
    ap.add_argument("--vectors", type=Path, help="assistant_proto/vectors/forms.v1.jsonl")
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--grammar", action=argparse.BooleanOptionalAction, required=True)
    ap.add_argument("--require-latency", action="store_true")
    ap.add_argument("--config", type=Path, help="학습 run_config.json — 보고서에 함께 적는다")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--json", type=Path, help="요약 수치를 JSON 으로도 (모델 카드용)")
    a = ap.parse_args(argv)

    exs = [e for p in a.data for e in read_examples(p)]
    if a.vectors:
        exs += load_vectors(a.vectors)
    preds = read_predictions(a.pred)
    rows = [score_one(e, preds.get(e.id)) for e in exs]
    s = summarize(rows)
    gates = gate_results(s, a.grammar, a.require_latency)
    config = json.loads(a.config.read_text(encoding="utf-8")) if a.config else None
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(
        render_report(a.title, s, rows, gates, {e.id: e for e in exs}, preds, config), encoding="utf-8"
    )
    if a.json:
        a.json.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=1), encoding="utf-8")
    for g in gates:
        print(f"{g.name:20s} {g.value:>22s}  {g.threshold:>12s}  {g.passed}")
    return 0 if all(g.passed is not False for g in gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 통과**

Run: `cd ml && uv run pytest tests/test_score.py -q` → `8 passed`.

- [ ] **Step 4: 커밋**

```bash
git add ml/esc_ml/score.py ml/tests/test_score.py
git commit -m "feat(ml): 채점기 — 해석기로 푼 값 비교, 합격선 판정, 보고서"
```

---

### Task 7: 예측기 · 하네스 묶음 · 일치 비교 (선행: PR A 머지)

**Files:**
- Create: `ml/esc_ml/hf.py`, `ml/esc_ml/predict_hf.py`, `ml/esc_ml/suite.py`, `ml/esc_ml/agree.py`
- Test: `ml/tests/test_predict.py`, `ml/tests/test_suite_agree.py`

**Interfaces:**
- Consumes: `assistant_proto.SYSTEM_PROMPT`, `json_schema`, `canonical_json`, `parse_form`, `form_to_dict`, `FormError`; `esc_ml.records`
- Produces:
  - `hf.load_model(model_id, quant="none", adapter=None)`, `hf.load_tokenizer(model_id)`
  - `predict_hf.build_messages(ex, fewshot) -> list[dict]`, `predict_hf.pick_fewshot(pool, k, seed) -> list[Example]`, CLI `python -m esc_ml.predict_hf --model … [--adapter …] --data … [--vectors …] [--fewshot-pool … --k 6] [--quant none|4bit] [--limit N] --out preds/x.jsonl`
  - `suite.build_suite(examples, gbnf=None) -> dict` (Task 1 의 묶음 모양), CLI `python -m esc_ml.suite --data … [--vectors …] [--gbnf …] [--limit N] --out spike/suites/<이름>.json`
  - `agree.agreement(a, b, ids) -> tuple[int, int, list[str]]`, CLI `python -m esc_ml.agree --a … --b … --suite …`

- [ ] **Step 1: 실패 테스트**

`ml/tests/test_predict.py`:
```python
from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json

from esc_ml.predict_hf import build_messages, pick_fewshot
from esc_ml.records import Example


def ex(i, intent):
    form = {"v": 1, "intent": intent, "target": {}, "set": {}}
    return Example(i, "train", f"{intent}/01", "2026-11-25T10:00:00+09:00", FIRST_PREFIX, f"문장 {i}", form)


POOL = [ex(f"p{i}", intent) for i, intent in enumerate(["cancel", "unknown", "cancel", "ask.requests", "unknown"])]


def test_build_messages_with_fewshot():
    msgs = build_messages(ex("t", "cancel"), POOL[:2])
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert [m["role"] for m in msgs[1:]] == ["user", "assistant", "user", "assistant", "user"]
    assert msgs[2]["content"] == canonical_json(POOL[0].form)
    assert msgs[-1]["content"] == FIRST_PREFIX + "문장 t"


def test_pick_fewshot_distinct_intents_and_deterministic():
    got = pick_fewshot(POOL, k=3, seed=1)
    assert len(got) == 3 and len({e.form["intent"] for e in got}) == 3
    assert got == pick_fewshot(POOL, k=3, seed=1)
```

`ml/tests/test_suite_agree.py`:
```python
from assistant_proto import FIRST_PREFIX, SYSTEM_PROMPT, canonical_json, json_schema

from esc_ml.agree import agreement
from esc_ml.records import Example, Prediction
from esc_ml.suite import build_suite

FORM = {"v": 1, "intent": "exam.remove", "target": {"rooms": ["801"]}, "set": {}}
EX = Example("v-1", "test", "vector", "2026-11-25T10:00:00+09:00", FIRST_PREFIX, "801 시험기간 없애줘", FORM)


def test_build_suite_shape():
    s = build_suite([EX], gbnf="root ::= x")
    assert s["system_prompt"] == SYSTEM_PROMPT and s["json_schema"] == json_schema()
    assert s["gbnf"] == "root ::= x"
    assert s["examples"] == [{"id": "v-1", "user": FIRST_PREFIX + "801 시험기간 없애줘", "gold": FORM}]


def test_agreement_compares_parsed_forms():
    text = canonical_json(FORM)
    spaced = text.replace(",", ", ")
    a = {"x": Prediction("x", text), "y": Prediction("y", text), "z": Prediction("z", "깨짐")}
    b = {"x": Prediction("x", spaced), "y": Prediction("y", text.replace("801", "803")), "z": Prediction("z", "깨짐")}
    same, total, diffs = agreement(a, b, ["x", "y", "z"])
    assert (same, total) == (1, 3) and diffs == ["y", "z"]
```

Run: `cd ml && uv run pytest tests/test_predict.py tests/test_suite_agree.py -q` → FAIL.

- [ ] **Step 2: 구현**

`ml/esc_ml/hf.py`:
```python
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
```

`ml/esc_ml/predict_hf.py`:
```python
"""HF transformers 로 예측 — 원본 기준 점수(예문 몇 개)·튜닝 모델·병합 모델 공용. 출력 = Prediction JSONL."""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

from assistant_proto import SYSTEM_PROMPT, canonical_json

from esc_ml.hf import DEFAULT_MODEL, load_model, load_tokenizer
from esc_ml.records import Example, Prediction, load_vectors, read_examples, write_predictions


def build_messages(ex: Example, fewshot: list[Example]) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for s in fewshot:
        msgs += [
            {"role": "user", "content": s.user_text()},
            {"role": "assistant", "content": canonical_json(s.form)},
        ]
    msgs.append({"role": "user", "content": ex.user_text()})
    return msgs


def pick_fewshot(pool: list[Example], k: int, seed: int) -> list[Example]:
    """intent 가 겹치지 않게 k 개 — 학습 데이터(생성)에서만 고른다(시험 문장·계약 예문 금지)."""
    rng = random.Random(seed)
    shuffled = pool[:]
    rng.shuffle(shuffled)
    out, seen = [], set()
    for e in shuffled:
        if e.form["intent"] not in seen:
            out.append(e)
            seen.add(e.form["intent"])
        if len(out) == k:
            break
    return out


def generate(model, tok, msgs: list[dict], max_new_tokens: int = 256) -> str:
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = tok(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
    out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False)
    return tok.decode(out[0, ids["input_ids"].shape[1] :], skip_special_tokens=True).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.predict_hf", description="HF 예측")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--adapter")
    ap.add_argument("--quant", default="none", choices=("none", "4bit"))
    ap.add_argument("--data", type=Path, nargs="*", default=[])
    ap.add_argument("--vectors", type=Path)
    ap.add_argument("--fewshot-pool", type=Path)
    ap.add_argument("--k", type=int, default=0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    exs = [e for p in a.data for e in read_examples(p)]
    if a.vectors:
        exs += load_vectors(a.vectors)
    if a.limit:
        exs = exs[: a.limit]
    shots = pick_fewshot(read_examples(a.fewshot_pool), a.k, a.seed) if a.k else []
    tok = load_tokenizer(a.model)
    model = load_model(a.model, a.quant, a.adapter)
    preds = []
    for i, e in enumerate(exs, 1):
        t0 = time.perf_counter()
        text = generate(model, tok, build_messages(e, shots))
        preds.append(Prediction(e.id, text, None))  # GPU 시간은 관리자 PC 응답 시간이 아니라 기록하지 않는다
        if i % 20 == 0:
            print(f"{i}/{len(exs)} ({time.perf_counter() - t0:.2f}s/문장)")
    write_predictions(a.out, preds)
    print(f"예측 {len(preds)}개 → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`ml/esc_ml/suite.py`:
```python
"""브라우저 하네스 묶음 — {system_prompt, json_schema, gbnf, examples:[{id,user,gold}]} (Task 1 모양)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assistant_proto import SYSTEM_PROMPT, json_schema

from esc_ml.records import Example, load_vectors, read_examples


def build_suite(examples: list[Example], gbnf: str | None = None) -> dict:
    return {
        "system_prompt": SYSTEM_PROMPT,
        "json_schema": json_schema(),
        "gbnf": gbnf,
        "examples": [{"id": e.id, "user": e.user_text(), "gold": e.form} for e in examples],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.suite", description="하네스 묶음 만들기")
    ap.add_argument("--data", type=Path, nargs="*", default=[])
    ap.add_argument("--vectors", type=Path)
    ap.add_argument("--gbnf", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    exs = [e for p in a.data for e in read_examples(p)]
    if a.vectors:
        exs += load_vectors(a.vectors)
    if a.limit:
        exs = exs[: a.limit]
    gbnf = a.gbnf.read_text(encoding="utf-8") if a.gbnf else None
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(build_suite(exs, gbnf), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.out} — {len(exs)}문장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`ml/esc_ml/agree.py`:
```python
"""두 예측 묶음 일치 비교 — 양자화 전(HF 병합 모델)·후(브라우저 배포 모델)가 같은 양식을 내는가."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assistant_proto import FormError, canonical_json, form_to_dict, parse_form

from esc_ml.records import Prediction, read_predictions


def _norm(p: Prediction | None) -> str | None:
    if p is None:
        return None
    try:
        return canonical_json(form_to_dict(parse_form(p.text.strip())))
    except (FormError, ValueError):
        return None


def agreement(a: dict[str, Prediction], b: dict[str, Prediction], ids: list[str]) -> tuple[int, int, list[str]]:
    """(같은 수, 전체, 다른 id). 둘 다 형식 오류여도 '다름'으로 센다."""
    diffs = []
    for i in ids:
        x, y = _norm(a.get(i)), _norm(b.get(i))
        if x is None or x != y:
            diffs.append(i)
    return len(ids) - len(diffs), len(ids), diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.agree", description="예측 일치 비교")
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--suite", type=Path, required=True, help="비교할 문장 id 를 이 묶음에서 읽는다")
    a = ap.parse_args(argv)
    ids = [e["id"] for e in json.loads(a.suite.read_text(encoding="utf-8"))["examples"]]
    same, total, diffs = agreement(read_predictions(a.a), read_predictions(a.b), ids)
    print(f"일치 {same}/{total}")
    for d in diffs:
        print(" 다름:", d)
    return 0 if same == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 통과**

Run: `cd ml && uv run pytest -q` → 모든 테스트 통과(이 Task 4개 포함).
Run: `uv run ruff check . && uv run ruff format --check .` → 통과.

- [ ] **Step 4: 커밋 + PR ②**

```bash
git add ml/esc_ml/hf.py ml/esc_ml/predict_hf.py ml/esc_ml/suite.py ml/esc_ml/agree.py \
  ml/tests/test_predict.py ml/tests/test_suite_agree.py
git commit -m "feat(ml): 예측기(HF)·하네스 묶음·양자화 전후 일치 비교"
```
PR ② `feat(ml): 학습 데이터·채점 파이프라인` (Task 2~7). 본문: Task 요약, `uv run pytest -q` 결과, CI `ml` job 녹색. (`ci.yml` 이 바뀌므로 cw 리뷰.)

---

### Task 8: 원본 E2B 기준 점수 (선행: Task 5·6·7, GPU)

**Files:**
- Create: `ml/reports/baseline-e2b.md`, `ml/reports/baseline-e2b.json`

실험 Task — 명령과 기록, 판정만.

- [ ] **Step 1: Gemma 4 지원 확인**

```bash
cd ml && uv sync --extra train
uv run python -c "from transformers import AutoConfig; print(AutoConfig.from_pretrained('google/gemma-4-E2B-it').model_type)"
```
Expected: 모델 종류 문자열 출력. `KeyError`/`ValueError: … does not recognize this architecture` 면 `uv lock --upgrade-package transformers && uv sync --extra train` 후 다시. 그래도 안 되면 `google/gemma-4-E2B-it` 의 모델 카드에 적힌 transformers 최소 판으로 `pyproject.toml` 의 `transformers>=` 를 올린다. 저장소 이름이 다르면(Hugging Face 에서 "gemma-4-E2B-it" 검색) `esc_ml/hf.py` 의 `DEFAULT_MODEL` 을 실제 이름으로 고친다.

- [ ] **Step 2: 예측 (예문 0개, 6개)**

```bash
uv run python -m esc_ml.gen --n 8000 --seed 7 --out data/gen
uv run python -m esc_ml.predict_hf --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --out preds/baseline-e2b-k0.jsonl
uv run python -m esc_ml.predict_hf --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --fewshot-pool data/gen/train.jsonl --k 6 --out preds/baseline-e2b-k6.jsonl
```
GPU 가 없으면 Kaggle 에서(Task 9 Step 1 과 같은 준비) 같은 명령.

- [ ] **Step 3: 채점·기록**

```bash
uv run python -m esc_ml.score --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --pred preds/baseline-e2b-k6.jsonl --no-grammar --title "기준 점수 — 원본 Gemma 4 E2B + 예문 6개" \
  --out reports/baseline-e2b.md --json reports/baseline-e2b.json
uv run python -m esc_ml.score --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --pred preds/baseline-e2b-k0.jsonl --no-grammar --title "기준 점수 — 원본 Gemma 4 E2B 예문 없음" \
  --out reports/baseline-e2b-k0.md
```
종료 코드 1(불합격)이 정상이다 — 기준 점수다. `reports/baseline-e2b.md` 맨 아래에 직접 적는다: "튜닝 목표 = 이 수치에서 합격선까지. 가장 많이 틀린 intent 3개: …".

- [ ] **Step 4: 커밋**

```bash
git add ml/reports/baseline-e2b.md ml/reports/baseline-e2b.json ml/reports/baseline-e2b-k0.md
git commit -m "feat(ml): 원본 Gemma 4 E2B 기준 점수 (예문 0·6개)"
```

---

### Task 9: LoRA 학습 (선행: Task 3·4, GPU)

**Files:**
- Create: `ml/esc_ml/train.py`, `ml/esc_ml/merge.py`, `ml/notebooks/kaggle_train.md`
- Test: `ml/tests/test_train.py`
- Create (학습 후): `ml/reports/run-<YYYYMMDD>-<n>.md`

**Interfaces:**
- Consumes: `esc_ml.records`, `esc_ml.hf`
- Produces: `train.to_prompt_completion(tok, ex) -> {"prompt": str, "completion": str}`, `train.data_digest(paths) -> str`, CLI `python -m esc_ml.train --train … --val … --out runs/<이름> [--quant 4bit] …` → `runs/<이름>/adapter/`, `runs/<이름>/run_config.json`; CLI `python -m esc_ml.merge --adapter … --out out/merged`

- [ ] **Step 1: 실패 테스트**

`ml/tests/test_train.py`:
```python
import pytest
from assistant_proto import FIRST_PREFIX, canonical_json

from esc_ml.records import Example
from esc_ml.train import data_digest, to_prompt_completion

EX = Example(
    "g1", "train", "cancel/01", "2026-11-25T10:00:00+09:00", FIRST_PREFIX, "취소",
    {"v": 1, "intent": "cancel", "target": {}, "set": {}},
)


class FakeTok:
    bos_token = "<bos>"

    def apply_chat_template(self, msgs, tokenize=False, add_generation_prompt=False, enable_thinking=False):
        s = "<bos>" + "".join(f"<{m['role']}>{m['content']}<end>" for m in msgs)
        return s + ("<assistant>" if add_generation_prompt else "")


class BadTok(FakeTok):
    def apply_chat_template(self, msgs, tokenize=False, add_generation_prompt=False, enable_thinking=False):
        out = super().apply_chat_template(msgs, tokenize, add_generation_prompt, enable_thinking)
        return out.replace("<assistant>", "<model>") if add_generation_prompt else out


def test_prompt_completion_split():
    pc = to_prompt_completion(FakeTok(), EX)
    assert not pc["prompt"].startswith("<bos>")  # 토크나이저가 BOS 를 다시 붙인다
    assert pc["prompt"].endswith("<user>관리자: 취소<end><assistant>")
    assert pc["completion"] == canonical_json(EX.form) + "<end>"


def test_template_mismatch_raises():
    with pytest.raises(ValueError):
        to_prompt_completion(BadTok(), EX)


def test_data_digest_changes_with_content(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text("x\n", encoding="utf-8")
    d1 = data_digest([p])
    p.write_text("y\n", encoding="utf-8")
    assert d1 != data_digest([p]) and len(d1) == 12
```

Run: `cd ml && uv run pytest tests/test_train.py -q` → FAIL.

- [ ] **Step 2: 구현**

`ml/esc_ml/train.py`:
```python
"""LoRA SFT — 정답(양식 JSON)에만 손실을 거는 prompt-completion 형식. 생각 모드는 끈다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from esc_ml.hf import DEFAULT_MODEL, load_model, load_tokenizer
from esc_ml.records import Example, read_examples


def to_prompt_completion(tok, ex: Example) -> dict:
    msgs = ex.messages()
    full = tok.apply_chat_template(msgs, tokenize=False, enable_thinking=False)
    prompt = tok.apply_chat_template(
        msgs[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    if not full.startswith(prompt):
        raise ValueError("chat template: 생성 프롬프트가 전체 대화의 앞부분이 아니다 — 템플릿 확인")
    completion = full[len(prompt) :]
    bos = getattr(tok, "bos_token", None)
    if bos and prompt.startswith(bos):
        prompt = prompt[len(bos) :]  # 토크나이저가 다시 붙이므로 두 번 들어가지 않게
    return {"prompt": prompt, "completion": completion}


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
    ap.add_argument("--quant", default="none", choices=("none", "4bit"), help="T4·P100 은 4bit(QLoRA)")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)

    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from trl import SFTConfig, SFTTrainer

    tok = load_tokenizer(a.model)
    train_rows = [e for p in a.train for e in read_examples(p) if e.split == "train"]
    val_rows = [e for p in a.val for e in read_examples(p) if e.split == "val"]
    train = Dataset.from_list([to_prompt_completion(tok, e) for e in train_rows])
    val = Dataset.from_list([to_prompt_completion(tok, e) for e in val_rows])

    model = load_model(a.model, a.quant)
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
        r=a.rank, lora_alpha=a.alpha, lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM"
    )
    trainer = SFTTrainer(
        model=model, args=cfg, train_dataset=train, eval_dataset=val, processing_class=tok, peft_config=peft_cfg
    )
    trainer.train()
    trainer.save_model(str(a.out / "adapter"))

    import peft
    import transformers
    import trl

    run = {
        "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()},
        "train_n": len(train_rows),
        "val_n": len(val_rows),
        "train_digest": data_digest(a.train),
        "val_digest": data_digest(a.val),
        "versions": {"transformers": transformers.__version__, "trl": trl.__version__, "peft": peft.__version__},
        "final": {k: v for k, v in trainer.state.log_history[-1].items()},
        "best_eval_loss": trainer.state.best_metric,
    }
    (a.out / "run_config.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(run["final"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`ml/esc_ml/merge.py`:
```python
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
```

- [ ] **Step 3: 통과**

Run: `cd ml && uv run pytest tests/test_train.py -q` → `3 passed`.

- [ ] **Step 4: Kaggle 실행 절차**

`ml/notebooks/kaggle_train.md`:
```markdown
# Kaggle 학습 절차 (GPU T4×2 또는 P100, 주 30시간 무료)

Settings → Accelerator: GPU. Add-ons → Secrets: `HF_TOKEN`(데이터 저장소 읽기·Gemma 다운로드), 저장소가 비공개면 `GITHUB_TOKEN`.

셀 1 — 코드·의존성
    import os
    from kaggle_secrets import UserSecretsClient
    sec = UserSecretsClient()
    os.environ["HF_TOKEN"] = sec.get_secret("HF_TOKEN")
    !git clone https://github.com/4thIS/Woo-ESC-Capston.git
    # 비공개면: !git clone https://$(python -c "print(sec.get_secret('GITHUB_TOKEN'))")@github.com/4thIS/Woo-ESC-Capston.git
    %cd Woo-ESC-Capston
    !pip install -q -e ./assistant_proto -e "./ml[train,release]"

셀 2 — 데이터 (생성은 seed 로 똑같이 재현, 다양화는 HF 데이터 저장소에서)
    %cd ml
    !python -m esc_ml.gen --n 8000 --seed 7 --out data/gen
    !python -c "from huggingface_hub import snapshot_download; snapshot_download('HF_OWNER/esc-assistant-data', repo_type='dataset', local_dir='data', allow_patterns=['para/*'])"

셀 3 — 학습 (T4·P100 은 bf16 이 없어 --quant 4bit)
    !python -m esc_ml.train --train data/gen/train.jsonl data/para/train.jsonl --val data/gen/val.jsonl data/para/val.jsonl \
        --out /kaggle/working/run1 --quant 4bit

셀 4 — 검증 문장으로 바로 예측(배포 전 감 잡기)
    !python -m esc_ml.predict_hf --adapter /kaggle/working/run1/adapter --quant 4bit --data data/gen/val.jsonl --limit 200 --out /kaggle/working/run1/preds-val.jsonl
    !python -m esc_ml.score --data data/gen/val.jsonl --pred /kaggle/working/run1/preds-val.jsonl --no-grammar --title "run1 검증" --out /kaggle/working/run1/val.md

출력(/kaggle/working/run1 의 adapter/, run_config.json, val.md)을 내려받아 로컬 ml/runs/run1/ 에 둔다(커밋 안 함).
`HF_OWNER` 는 spec §17 에서 정한 계정·조직으로 바꿔 쓴다.
```

- [ ] **Step 5: 학습 실행·보고서**

1. 다양화 데이터 업로드(학습 전 1회): `uv run --extra release python -m esc_ml.release upload-data --folder data/para --repo $HF_OWNER/esc-assistant-data` (Task 11 Step 2 의 함수 — Task 11 Step 1~3 을 먼저 구현해 둔다).
2. Kaggle 절차 셀 1~4 실행.
3. 시험 세트 예측·채점(로컬 GPU 또는 Kaggle):
```bash
uv run python -m esc_ml.predict_hf --adapter runs/run1/adapter --data data/test_human.jsonl \
  --vectors ../assistant_proto/vectors/forms.v1.jsonl --out preds/run1-hf.jsonl
uv run python -m esc_ml.score --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --pred preds/run1-hf.jsonl --no-grammar --config runs/run1/run_config.json \
  --title "run1 — 튜닝 E2B (HF, 양자화 전)" --out reports/run-<YYYYMMDD>-1.md
```
판정(양자화 전 감 잡기 — 최종 합격은 Task 10): 합격선을 넘으면 Task 10 으로. 못 넘으면 보고서의 "intent 별"·"틀린 문장"을 보고 **틀린 유형에 맞는 문장 틀·가상 값을 Task 3 에 더해** 다시 생성 → 재학습(run2, run3). 같은 데이터로 하이퍼파라미터만 바꾸는 시도는 2번까지(lr 1e-4 / epochs 5). 3회 안에 칸 정확도가 90% 아래면 Task 11 Step 6 (E4B 분기)로.

- [ ] **Step 6: 커밋**

```bash
git add ml/esc_ml/train.py ml/esc_ml/merge.py ml/notebooks/kaggle_train.md ml/tests/test_train.py
git commit -m "feat(ml): LoRA 학습·병합 — prompt-completion(정답에만 손실), Kaggle 절차"
git add ml/reports/run-<YYYYMMDD>-1.md
git commit -m "feat(ml): run1 학습 보고서"
```

---

### Task 10: 병합 · 변환 · 양자화 · 배포 모델 평가 (선행: Task 1 판정 + Task 9)

**Files:**
- Create: `ml/reports/quant-<YYYYMMDD>.md`, `ml/reports/quant-<YYYYMMDD>.json`
- 산출물(커밋 안 함): `ml/out/merged/`, `ml/spike/models/<배포 폴더>/`

**게이트:** `ml/reports/spike.md` 의 `runtime` 값으로 아래 갈래 **하나만** 실행한다. Task 1 Step 9 에서 원본으로 이미 통과한 명령이므로 같은 명령에 입력만 `ml/out/merged` 로 바꾼다.

- [ ] **Step 1: 병합 + 양자화 전 예측(비교 기준)**

```bash
cd ml
uv run python -m esc_ml.merge --adapter runs/run1/adapter --out out/merged
uv run python -m esc_ml.suite --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --out spike/suites/test.json
uv run python -m esc_ml.suite --vectors ../assistant_proto/vectors/forms.v1.jsonl --limit 20 --out spike/suites/agree20.json
uv run python -m esc_ml.predict_hf --model out/merged --vectors ../assistant_proto/vectors/forms.v1.jsonl --limit 20 \
  --out preds/merged-agree20.jsonl
```

- [ ] **Step 2 (갈래 A — `runtime: wllama`): GGUF + GBNF**

```bash
cd ml/out && git clone --depth 1 https://github.com/ggml-org/llama.cpp && cd llama.cpp
pip install -r requirements/requirements-convert_hf_to_gguf.txt
cmake -B build && cmake --build build --config Release -j
python convert_hf_to_gguf.py ../merged --outfile ../esc-e2b-f16.gguf --outtype f16
./build/bin/llama-quantize ../esc-e2b-f16.gguf ../esc-e2b-q4_k_m.gguf Q4_K_M
mkdir -p ../../spike/models/esc-wllama
./build/bin/llama-gguf-split --split --split-max-size 512M ../esc-e2b-q4_k_m.gguf ../../spike/models/esc-wllama/esc-e2b-q4_k_m
uv run --project ../.. python -c "import json; from assistant_proto import json_schema; open('../form.schema.json','w',encoding='utf-8').write(json.dumps(json_schema(), ensure_ascii=False))"
python examples/json_schema_to_grammar.py ../form.schema.json > ../../spike/models/esc-wllama/form.gbnf
```
하네스 모델 칸: `models/esc-wllama/esc-e2b-q4_k_m-00001-of-0000N.gguf, …`(만들어진 조각 전부, 쉼표). 묶음은 `--gbnf spike/models/esc-wllama/form.gbnf` 를 붙여 Step 1 의 두 `esc_ml.suite` 명령을 다시 만든다.

- [ ] **Step 2 (갈래 B — `runtime: webllm`): MLC**

```bash
pip install --pre -U -f https://mlc.ai/wheels mlc-llm-nightly-cpu mlc-ai-nightly-cpu
mlc_llm convert_weight ml/out/merged --quantization q4f16_1 -o ml/spike/models/esc-webllm
mlc_llm gen_config ml/out/merged --quantization q4f16_1 --conv-template gemma_instruction -o ml/spike/models/esc-webllm
mlc_llm compile ml/spike/models/esc-webllm/mlc-chat-config.json --device webgpu -o ml/spike/models/esc-webllm/lib.wasm
```
`--device webgpu` 컴파일은 emscripten 이 필요하다(MLC 문서 "WebLLM 모델 컴파일" 절차대로 `emsdk` 설치·활성화). Gemma 4 대화 틀 이름이 `gemma_instruction` 과 다르면 `mlc_llm gen_config --help` 의 목록에서 gemma 계열 최신 이름으로. 하네스 모델 칸: `models/esc-webllm`.

- [ ] **Step 2 (갈래 C — `runtime: transformers`): ONNX q4f16**

```bash
git clone --depth 1 https://github.com/huggingface/transformers.js ml/out/transformers.js
cd ml/out/transformers.js && pip install -r scripts/requirements.txt
python -m scripts.convert --model_id ../merged --quantize --modes q4f16 --output_parent_dir ../../spike/models
```
출력 폴더 이름(`../../spike/models/merged`)을 `esc-onnx` 로 바꾼다. 하네스 모델 칸: `models/esc-onnx`.

- [ ] **Step 2 (갈래 D — `runtime: litert`): LiteRT(.litertlm/.task)**

Task 1 Step 9 에서 통과한 변환 명령(LiteRT-LM 문서 또는 `ai-edge-torch` 의 Gemma 변환 예제 — 실제 쓴 명령을 `spike.md` 에 적어 둔다)을 `ml/out/merged` 로 실행해 `ml/spike/models/esc-litert/esc-e2b-int4.task` 를 만든다. 하네스 모델 칸: `models/esc-litert/esc-e2b-int4.task`. 생성 함수가 대화 틀을 씌우므로 `adapters/mediapipe.js` 의 `PROMPT` 가 튜닝 때 쓴 chat template 과 같은지 `uv run python -c "from esc_ml.hf import load_tokenizer; t=load_tokenizer('out/merged'); print(repr(t.apply_chat_template([{'role':'system','content':'S'},{'role':'user','content':'U'}], tokenize=False, add_generation_prompt=True, enable_thinking=False)))"` 로 확인하고 다르면 `PROMPT` 를 그 모양으로 고친다(그 수정도 커밋).

- [ ] **Step 3: 하네스로 배포 모델 평가 (wj 노트북)**

```bash
python ml/spike/serve.py
```
브라우저: 도구 = 선택 도구, 모델 = 위 갈래의 값, 묶음 = `suites/agree20.json` → [불러오기] → [실행] → [내보내기] → `ml/preds/quant-agree20.jsonl`.
묶음 = `suites/test.json` 으로 다시 [실행] → `ml/preds/quant-test.jsonl`.

```bash
cd ml
uv run python -m esc_ml.agree --a preds/merged-agree20.jsonl --b preds/quant-agree20.jsonl --suite spike/suites/agree20.json
uv run python -m esc_ml.score --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --pred preds/quant-test.jsonl --grammar --title "배포 후보 — 튜닝 E2B, <도구> 양자화 (wj 노트북)" \
  --out reports/quant-<YYYYMMDD>.md --json reports/quant-<YYYYMMDD>.json
```
(`--grammar` 는 문법 강제 도구일 때만, 아니면 `--no-grammar`.)

판정:
- 일치 20/20 → 다음. 18~19 → 다른 문장을 `quant-…md` 에 적고 진행(최종 판단은 시험 세트 합격선). 17 이하 → 양자화를 한 단계 올려(A: `Q5_K_M`, B: `q4f32_1`, C: `q8`) 다시.
- 시험 세트 합격선(응답 시간 제외) 모두 통과 → Task 11. 하나라도 불합격 → Task 9 Step 5 의 데이터 보강·재학습으로 돌아간다.

- [ ] **Step 4: 커밋**

```bash
git add ml/reports/quant-<YYYYMMDD>.md ml/reports/quant-<YYYYMMDD>.json
git commit -m "feat(ml): 배포 후보 양자화 모델 평가 — 합격선 표, 양자화 전후 일치"
```
PR ③ `feat(ml): 기준 점수·학습·양자화 보고서` (Task 8~10 보고서). 본문에 합격선 표 복사.

---

### Task 11: 릴리스 — Hugging Face 업로드 · 관리자 PC 확인 · `model.json` (선행: Task 10 합격, 01 의 `model.json` 존재, HF 조직 결정)

**Files:**
- Create: `ml/esc_ml/release.py`, `ml/tests/test_release.py`
- Create (릴리스마다): `ml/reports/release-v<X.Y.Z>.md`
- Modify (릴리스 PR): `server/app/assistant/model.json` (01 이 만든 파일 — 값만 바꾼다, cw 머지)

**Interfaces:**
- Consumes: 부록 §4.1 키 (`runtime`, `repo`, `revision`, `files[{name,size,sha256}]`, `generation`); `ml/reports/quant-*.json`
- Produces: `release.RUNTIMES`, `release.file_manifest(folder) -> list[dict]`, `release.model_json(runtime, repo, revision, files, temperature=0, max_tokens=256) -> dict`, `release.render_card(version, base_model, runtime, summary, n_train) -> str`, `release.upload_model(folder, repo, tag) -> str`(커밋 해시), `release.upload_data(folder, repo) -> str`; CLI `python -m esc_ml.release {manifest|card|upload-model|upload-data|model-json}`

`model.json` 에 `"enabled": true` 를 함께 쓴다(부록 §4.1 의 "있을 때" 응답 첫 키). 01 이 만든 파일 모양이 다르면 그 모양을 따르고 이 Task 의 `model_json` 을 맞춘다.

- [ ] **Step 1: 실패 테스트**

`ml/tests/test_release.py`:
```python
import hashlib

import pytest

from esc_ml.release import file_manifest, model_json, render_card

REV = "0123456789abcdef0123456789abcdef01234567"


def test_file_manifest(tmp_path):
    (tmp_path / "a.gguf").write_bytes(b"abc")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"xy")
    (tmp_path / "README.md").write_text("card", encoding="utf-8")
    (tmp_path / ".gitattributes").write_text("*", encoding="utf-8")
    got = file_manifest(tmp_path)
    assert got == [
        {"name": "a.gguf", "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()},
        {"name": "sub/b.bin", "size": 2, "sha256": hashlib.sha256(b"xy").hexdigest()},
    ]


def test_model_json_shape():
    files = [{"name": "a.gguf", "size": 3, "sha256": "x" * 64}]
    got = model_json("wllama", "org/esc-assistant-e2b", REV, files)
    assert got == {
        "enabled": True,
        "runtime": "wllama",
        "repo": "org/esc-assistant-e2b",
        "revision": REV,
        "files": files,
        "generation": {"temperature": 0, "max_tokens": 256},
    }


def test_model_json_rejects_bad_values():
    with pytest.raises(ValueError):
        model_json("onnx", "org/x", REV, [])
    with pytest.raises(ValueError):
        model_json("wllama", "org/x", "main", [])


def test_card_mentions_metrics_and_data():
    s = {"n": 320, "intent_acc": 0.985, "field_acc": 0.961, "exact_acc": 0.93, "format_err": 0.0,
         "danger_rate": 0.0, "latency_mean_ms": 2100.0, "latency_p90_ms": 3200.0}
    md = render_card("1.0.0", "google/gemma-4-E2B-it", "wllama", s, n_train=9000)
    assert "98.5%" in md and "가상" in md and "Apache-2.0" in md and "1.0.0" in md
```

Run: `cd ml && uv run pytest tests/test_release.py -q` → FAIL.

- [ ] **Step 2: 구현**

`ml/esc_ml/release.py`:
```python
"""릴리스 — 파일 목록·SHA-256, 모델 카드, HF 업로드(커밋 해시로 고정), 서버 model.json 값."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

RUNTIMES = ("webllm", "transformers", "litert", "wllama")  # 부록 §4.1
SKIP = {"README.md", ".gitattributes"}
_REV = re.compile(r"^[0-9a-f]{40}$")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_manifest(folder) -> list[dict]:
    root = Path(folder)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name not in SKIP)
    return [{"name": p.relative_to(root).as_posix(), "size": p.stat().st_size, "sha256": _sha256(p)} for p in files]


def model_json(
    runtime: str, repo: str, revision: str, files: list[dict], temperature: float = 0, max_tokens: int = 256
) -> dict:
    if runtime not in RUNTIMES:
        raise ValueError(f"runtime 은 {RUNTIMES} 중 하나: {runtime}")
    if not _REV.match(revision):
        raise ValueError("revision 은 40자 커밋 해시여야 한다 (브랜치·태그 이름 금지)")
    return {
        "enabled": True,
        "runtime": runtime,
        "repo": repo,
        "revision": revision,
        "files": files,
        "generation": {"temperature": temperature, "max_tokens": max_tokens},
    }


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_card(version: str, base_model: str, runtime: str, summary: dict, n_train: int) -> str:
    lat = summary.get("latency_mean_ms")
    return f"""---
license: apache-2.0
base_model: {base_model}
language: [ko]
tags: [gemma4, lora, structured-output]
---

# ESC 관리자 AI 비서 — 문장 → 양식 해석 모델 v{version}

대학 강의실 게시 시스템(ESC)의 관리자 채팅 문장을 정해진 양식(JSON) 한 줄로 옮기는 모델이다.
날짜 계산·검증·적용은 서버가 하고, 이 모델은 문장 속 표현을 칸에 옮기기만 한다.

- 기반: `{base_model}` + LoRA 파인튜닝, 병합 후 양자화 (실행 도구: {runtime})
- 라이선스: Apache-2.0 (기반 모델 라이선스를 따른다)
- 입력: 시스템 지시문 + `관리자: <문장>` (대화 중이면 서버가 준 상태 접두어). 출력: 양식 JSON 한 줄

## 학습 데이터

- 문장 틀 × **가상** 값(가상 건물·강의실·과목·교수·학생)으로 만든 예문과, 그 예문을 Claude 로 표현만 바꾼 변형 — 총 {n_train:,}문장
- 실제 사람·학교 이름, 실제 운영 기록은 들어 있지 않다.
- 시험 문장(사람이 쓴 약 300문장)은 학습에 쓰지 않았다.

## 평가 (사람 시험 문장 + 계약 예문 {summary["n"]}문장, 이 양자화 모델)

| 지표 | 값 |
|---|---|
| intent 정확도 | {_pct(summary["intent_acc"])} |
| 칸 정확도 | {_pct(summary["field_acc"])} |
| 양식 전체 일치 | {_pct(summary["exact_acc"])} |
| 형식 오류 | {_pct(summary["format_err"])} |
| 위험 오류(추가·수정 → 삭제) | {_pct(summary["danger_rate"])} |
| 평균 응답 (학과 관리자 PC) | {f"{lat:.0f} ms" if lat is not None else "—"} |

## 한계

- 정해진 18가지 작업 밖의 요청은 `unknown` 으로 낸다.
- 출력은 제안일 뿐이며, 서버 검증과 관리자 확인 화면을 거쳐서만 반영된다.
"""


def upload_model(folder, repo: str, tag: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo, repo_type="model", exist_ok=True)
    info = api.upload_folder(folder_path=str(folder), repo_id=repo, repo_type="model", commit_message=f"release {tag}")
    api.create_tag(repo, tag=tag, revision=info.oid, repo_type="model")
    return info.oid


def upload_data(folder, repo: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    info = api.upload_folder(folder_path=str(folder), repo_id=repo, repo_type="dataset", path_in_repo=Path(folder).name)
    return info.oid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.release", description="릴리스 도우미")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--folder", type=Path, required=True)
    c = sub.add_parser("card")
    c.add_argument("--version", required=True)
    c.add_argument("--base", default="google/gemma-4-E2B-it")
    c.add_argument("--runtime", required=True, choices=RUNTIMES)
    c.add_argument("--summary", type=Path, required=True)
    c.add_argument("--n-train", type=int, required=True)
    c.add_argument("--out", type=Path, required=True)
    um = sub.add_parser("upload-model")
    um.add_argument("--folder", type=Path, required=True)
    um.add_argument("--repo", required=True)
    um.add_argument("--tag", required=True)
    ud = sub.add_parser("upload-data")
    ud.add_argument("--folder", type=Path, required=True)
    ud.add_argument("--repo", required=True)
    mj = sub.add_parser("model-json")
    mj.add_argument("--folder", type=Path, required=True)
    mj.add_argument("--runtime", required=True, choices=RUNTIMES)
    mj.add_argument("--repo", required=True)
    mj.add_argument("--revision", required=True)
    mj.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    if a.cmd == "manifest":
        print(json.dumps(file_manifest(a.folder), ensure_ascii=False, indent=1))
    elif a.cmd == "card":
        summary = json.loads(a.summary.read_text(encoding="utf-8"))
        a.out.write_text(render_card(a.version, a.base, a.runtime, summary, a.n_train), encoding="utf-8")
    elif a.cmd == "upload-model":
        print(upload_model(a.folder, a.repo, a.tag))
    elif a.cmd == "upload-data":
        print(upload_data(a.folder, a.repo))
    else:
        data = model_json(a.runtime, a.repo, a.revision, file_manifest(a.folder))
        a.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 통과·커밋**

Run: `cd ml && uv run pytest tests/test_release.py -q` → `4 passed`. `uv run pytest -q` 전체 통과.
```bash
git add ml/esc_ml/release.py ml/tests/test_release.py
git commit -m "feat(ml): 릴리스 도우미 — 파일 목록·SHA-256, 모델 카드, HF 업로드(커밋 해시), model.json 값"
```

- [ ] **Step 4: 후보 업로드 → 학과 관리자 PC 확인 → 태그**

```bash
cd ml
export HF_OWNER=…           # spec §17 결정
export HF_TOKEN=…           # 커밋 금지
uv run --extra release python -m esc_ml.release card --version 1.0.0 --runtime <도구> \
  --summary reports/quant-<YYYYMMDD>.json --n-train <학습 문장 수> --out spike/models/<배포 폴더>/README.md
uv run --extra release python -m esc_ml.release upload-model --folder spike/models/<배포 폴더> \
  --repo $HF_OWNER/esc-assistant-e2b --tag v1.0.0-rc1
```
출력된 40자 해시 = `REV`. 하네스 Space(Task 1 Step 7)에 `spike/suites/test.json` 을 올린 뒤(`upload_folder` 를 `allow_patterns=['suites/test.json']` 로), **학과 관리자 PC** 에서 Space 를 열어 모델 칸에 `https://huggingface.co/$HF_OWNER/esc-assistant-e2b/resolve/REV/<파일>`(조각이면 쉼표로 전부) → 묶음 `suites/test.json` → [불러오기]·[실행]·[내보내기] → `preds/release-adminpc.jsonl`.
```bash
uv run python -m esc_ml.score --data data/test_human.jsonl --vectors ../assistant_proto/vectors/forms.v1.jsonl \
  --pred preds/release-adminpc.jsonl --grammar --require-latency \
  --title "릴리스 v1.0.0 — 학과 관리자 PC" --out reports/release-v1.0.0.md --json reports/release-v1.0.0.json
```
종료 코드 0(응답 시간 포함 전부 합격)이면:
```bash
uv run --extra release python -c "from huggingface_hub import HfApi; HfApi().create_tag('$HF_OWNER/esc-assistant-e2b', tag='v1.0.0', revision='REV', repo_type='model')"
```
불합격이 응답 시간만이면 cw 에게 보고(spec §16 — 양자화 단계를 낮추거나 E4B/E2B 판단, 2단계 서버 측 실행 검토). 정확도 불합격이면 Task 9 로.

- [ ] **Step 5: `model.json` PR (cw 머지)**

```bash
uv run python -m esc_ml.release model-json --folder spike/models/<배포 폴더> --runtime <도구> \
  --repo $HF_OWNER/esc-assistant-e2b --revision REV --out ../server/app/assistant/model.json
git switch -c feature/ml-release-v1.0.0
git add server/app/assistant/model.json ml/reports/release-v1.0.0.md ml/reports/release-v1.0.0.json
git commit -m "feat(ml): 관리자 AI 비서 모델 v1.0.0 배포 — Gemma 4 E2B 튜닝, <도구>"
```
`model.json` 의 `files` 에는 모델 카드(`README.md`)가 빠져 있어야 한다(`file_manifest` 가 뺀다). PR 본문: 합격선 표(`release-v1.0.0.md` 의 표 그대로), HF 판 링크 `https://huggingface.co/$HF_OWNER/esc-assistant-e2b/tree/REV`, 롤백 방법 한 줄. **머지는 cw** — 머지 = 홈서버 반영(`esc-autodeploy`), 관리자 브라우저는 다음 방문에 새 판을 받는다.

롤백: 이 PR 을 `git revert` 하는 PR 하나(이전 `revision` 으로 돌아간다 — 첫 릴리스면 `{"enabled": false}`). HF 의 파일은 지우지 않는다(이전 판 해시가 계속 유효해야 한다).

- [ ] **Step 6: E4B 분기 (E2B 가 Task 9 의 3회 안에 합격하지 못했을 때만)**

같은 Task 9·10·11 을 `--model google/gemma-4-E4B-it` 로 반복한다. 차이:
- 학습: `--quant 4bit` 필수(16 GB GPU), `--batch 2 --grad-accum 8`.
- 저장소 이름: `$HF_OWNER/esc-assistant-e4b`, 모델 카드 `--base google/gemma-4-E4B-it`.
- 관리자 PC 응답 시간: Task 1 Step 8 의 E4B 측정값이 5초를 넘었으면 시작 전에 cw 에게 알린다(합격 불가능 — spec §16 재논의).

---

### Task 12: 전체 게이트 + PR (각 PR 마다)

- [ ] **Step 1: 게이트**

```bash
cd ml
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
git status --short   # data/gen·para·raw, runs, out, preds, spike/models 가 보이면 안 된다 (.gitignore 확인)
```
Expected: 린트 통과, 전부 passed, 대용량 파일 없음.

- [ ] **Step 2: PR**

| PR | 브랜치 | 제목 | 선행 |
|---|---|---|---|
| ① | `feature/ml-spike` | `feat(ml): 0단계 — 브라우저 실행 도구 실험` | 없음 |
| ② | `feature/ml-pipeline` | `feat(ml): 학습 데이터·채점 파이프라인` | 01 PR A |
| ③ | `feature/ml-train` | `feat(ml): 기준 점수·학습·양자화 보고서` | ② |
| ④ | `feature/ml-release-vX.Y.Z` | `feat(ml): 관리자 AI 비서 모델 vX.Y.Z 배포` | ③ + 01 백엔드 머지 |

본문 공통: Task 요약, 게이트 결과(명령과 출력 마지막 줄), 보고서 링크. ③·④ 는 합격선 표를 본문에 복사하고 각 줄을 체크한다:
```markdown
- [ ] intent 정확도 ≥ 97%
- [ ] 칸 정확도 ≥ 95%
- [ ] 양식 전체 일치 ≥ 90%
- [ ] 형식 오류 0% (문법 강제) / ≤ 1% (강제 없음)
- [ ] 위험 오류 ≤ 0.5%
- [ ] 학과 관리자 PC 평균 응답 ≤ 5초 (④만)
- [ ] 사람 시험 문장 ↔ 학습 겹침 0건 (`esc_ml.overlap`)
- [ ] 커밋에 모델·데이터 원본·토큰 없음
```
④ 는 `server/app/assistant/model.json` 을 바꾸므로 cw 리뷰·머지. attribution 줄은 쓰지 않는다.

## 이후

- 2단계: 서버에 쌓인 "모델이 틀리고 관리자가 고친 사례"를 가상화해 내보내는 도구(spec §8.6)가 생기면, 그 데이터를 `data/` 에 더해 Task 9~11 을 반복한다(v1.1.0 …).
- 규격 판(`SCHEMA_VERSION`)이 오르면: Task 3 틀·Task 1 의 임시 스키마가 아니라 `assistant_proto` 를 따라 재생성 → 재학습 → 새 릴리스. 서버가 판이 다른 출력을 409 로 거절하므로 모델 릴리스와 규격 머지 순서를 cw 와 맞춘다.
- 하네스(`ml/spike/`)는 이후 릴리스의 관리자 PC 확인에 계속 쓴다.
