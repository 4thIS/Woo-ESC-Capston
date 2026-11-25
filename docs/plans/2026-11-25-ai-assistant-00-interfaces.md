# 관리자 AI 비서 — 영역 간 인터페이스 (작업지시서 공통 부록)

- 생성일시: 2026-11-25
- 기준 spec: `docs/specs/2026-11-25-admin-ai-assistant-design.md`
- 이 문서를 쓰는 작업지시서:
  - `2026-11-25-ai-assistant-01-proto-backend.md` (cw — `assistant_proto/`·`server/app/assistant/`)
  - `2026-11-25-ai-assistant-02-finetune.md` (wj — `ml/`)
  - `2026-11-25-ai-assistant-03-web.md` (cw 화면 스펙 → wj `web/src/admin/assistant/`)

세 작업지시서는 **이 문서의 이름·모양만** 서로에게 기대한다. 여기를 바꾸면 세 문서를 함께 고친다. 실제 원본은 머지 후 `assistant_proto/`(§1~§3)와 서버 코드(§4~§5)다 — 이 문서는 그 원본이 생기기 전까지의 약속이다.

---

## 1. 양식(form) v1

### 1.1 JSON 모양

```json
{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"],"when":"이번 주 금요일","time":"15시부터 18시까지","type":"특강"}}
```

| 키 | 타입 | 규칙 |
|---|---|---|
| `v` | 정수 | 항상 `1` |
| `intent` | 문자열 | §1.2 의 18개 중 하나 |
| `target` | 객체 | `Fields` — 비어 있을 수 있음 |
| `set` | 객체 | `Fields` — 비어 있을 수 있음 |

`Fields` 가 가질 수 있는 키 (그 밖의 키는 규격 위반, `additionalProperties: false`):

| 키 | 타입 | 의미 |
|---|---|---|
| `rooms` | 문자열 배열 (1~30개, 각 1~20자) | 강의실 표현 그대로 ("803", "803호", "공학관 803", "8층 전체", "801~805") |
| `when` | 문자열 (1~40자) | 날짜·기간·요일 표현 그대로 ("이번 주 금요일", "12/15~19", "매주 월") |
| `time` | 문자열 (1~40자) | 시각 표현 그대로 ("15시부터 18시까지", "3시 반", "16시로") |
| `type` | 문자열 enum | `수업` `시험` `휴강` `빈강의실` `특강` `대여` 중 하나 |
| `subject` | 문자열 (1~40자) | 과목·행사 이름 그대로 |
| `professor` | 문자열 (1~20자) | 교수·담당자 이름 그대로 |
| `reason` | 문자열 (1~100자) | 거절 사유 그대로 |
| `requester` | 문자열 (1~20자) | 신청자 이름·학번 표현 그대로 |

값은 모두 **문장 속 표현을 그대로** 옮긴다(`type` 만 예외로 6개 중 고름). 빈 문자열·`null` 은 쓰지 않는다 — 없는 칸은 키를 빼고 낸다.

### 1.2 intent 18개

```
event.add  event.change  event.remove
exam.add   exam.change   exam.remove
class.add  class.change  class.remove
request.approve  request.reject
ask.free_rooms  ask.schedule  ask.requests  ask.node
fill  cancel  unknown
```

`type` 라벨 → 서버 type 코드: `수업`=1 `시험`=2 `휴강`=3 `빈강의실`=4 `특강`=5 `대여`=6.

### 1.3 정규 직렬화 (모델 출력 = 학습 정답)

모델은 아래 규칙으로 직렬화한 문자열 **하나만** 출력한다. 학습 정답도 같은 함수로 만든다.

- 키 순서: 최상위 `v`, `intent`, `target`, `set`. `Fields` 안은 `rooms`, `when`, `time`, `type`, `subject`, `professor`, `reason`, `requester` 순.
- 구분자 `,` `:` (공백 없음), `ensure_ascii=False`.
- Python: `assistant_proto.canonical_json(form: dict) -> str`.

---

## 2. 프롬프트 (모델 입력)

- 시스템 메시지: `assistant_proto.SYSTEM_PROMPT` (파일 `assistant_proto/prompt/system.v1.txt`, 한국어 고정 지시문 — 내용은 01 작업지시서가 정한다).
- 사용자 메시지 = `접두어 + 관리자 문장`.
  - 첫 턴 접두어: `assistant_proto.FIRST_PREFIX` = `"관리자: "`
  - 이어지는 턴 접두어: 서버가 턴 응답의 `next_prefix` 로 준다. 모양:

```
상태: event.add | 강의실 803호 | 날짜 이번주 금요일 | 시각 15시부터 18시까지 | 유형 특강 | 이름 ?
질문: 특강 이름은 무엇인가요?
관리자: 
```

  (마지막 줄 `관리자: ` 뒤에 문장을 붙인다. 줄바꿈은 `\n`.)
- 상태 값은 **해석한 값이 아니라 문장 속 표현 그대로**다("이번주 금요일"). 학습 데이터(`ml/`)가 DB 없이 서버와 글자 하나 다르지 않은 접두어를 만들 수 있게 하기 위해서다. 해석한 날짜·시각은 확인 화면에서 보인다.
- 칸 이름·질문 문장은 서버와 `ml/` 이 **같은 함수**로 만든다: `rules.state_items`·`rules.question` (§3).
- Python: `assistant_proto.render_prefix(intent: str, items: list[tuple[str, str | None]], question: str) -> str` — `items` 는 (칸 이름, 표시값 또는 `None`=빈 칸 `?`).
- 어시스턴트 메시지(정답) = `canonical_json(form)`.
- Gemma 4 생각 모드는 끈다. 생성 설정 기본: `temperature 0`, `max_tokens 256`.

---

## 3. `assistant_proto` Python 패키지 공개 API

위치 `assistant_proto/assistant_proto/`. DB·네트워크 없음. 서버와 `ml/` 이 경로 의존성으로 쓴다(`lora-proto` 와 같은 방식, 패키지 이름 `assistant-proto`).

```python
SCHEMA_VERSION: int = 1
INTENTS: tuple[str, ...]              # §1.2 순서
TYPE_LABELS: tuple[str, ...]          # ("수업","시험","휴강","빈강의실","특강","대여")
FIELD_ORDER: tuple[str, ...]          # §1.3 Fields 순서
SYSTEM_PROMPT: str
FIRST_PREFIX: str                     # "관리자: "

def json_schema() -> dict: ...        # form.v1.json 내용 (출력 문법 강제에 그대로 씀)
def type_code(label: str) -> int: ... # "특강" -> 5, 모르는 라벨이면 ValueError

class FormError(ValueError): ...

@dataclass(frozen=True)
class Fields:
    rooms: tuple[str, ...] | None = None
    when: str | None = None
    time: str | None = None
    type: str | None = None
    subject: str | None = None
    professor: str | None = None
    reason: str | None = None
    requester: str | None = None

@dataclass(frozen=True)
class Form:
    v: int
    intent: str
    target: Fields
    set: Fields

def parse_form(text_or_obj: str | dict) -> Form: ...   # JSON 문자열/객체 → Form, 규격 위반이면 FormError
def form_to_dict(form: Form) -> dict: ...              # 없는 칸은 키를 뺀 dict
def canonical_json(form: Form | dict) -> str: ...      # §1.3

def render_prefix(intent: str, items: list[tuple[str, str | None]], question: str) -> str: ...

# ---- 해석기 (assistant_proto.resolve) ----
@dataclass(frozen=True)
class When:
    kind: Literal["dates", "range", "weekdays"]
    dates: tuple[date, ...] = ()       # kind == "dates": 하나 이상, 오름차순
    start: date | None = None          # kind == "range"
    end: date | None = None            # kind == "range" (start <= end)
    weekdays: tuple[int, ...] = ()     # kind == "weekdays": 1=월 … 7=일, 오름차순

@dataclass(frozen=True)
class TimeSpan:
    start: time
    end: time | None                   # None = 시작만 말함("16시로")

def resolve_when(expr: str, now: datetime) -> When | None: ...   # now 는 KST aware. 못 풀면 None
def resolve_weekdays(expr: str) -> tuple[int, ...] | None: ...  # 1=월 … 7=일, 오름차순. 못 풀면 None
def resolve_time(expr: str) -> TimeSpan | None: ...
def normalize_room(expr: str) -> str: ...  # 공백·"호" 정리: "803호"→"803", "공학관 803 호"→"공학관 803". 범위·층 표현은 그대로

# ---- 대화 규칙 (assistant_proto.rules) — 서버가 되묻고, ml 이 같은 접두어를 만든다 ----
PRIMARY: dict[str, str]   # intent → 이어지는 답(fill)이 들어갈 칸 묶음 "set" | "target"
def missing(intent: str, target: dict, set_: dict) -> str | None: ...   # 다음에 물을 칸 "set.time" 등, 다 찼으면 None
def question(intent: str, slot: str, type_label: str | None = None) -> str: ...  # 그 칸을 묻는 문장
def state_items(intent: str, target: dict, set_: dict, missing_slot: str | None = None) -> list[tuple[str, str | None]]: ...
```

- 이어지는 답의 양식은 항상 `{"intent":"fill","target":{},"set":{<칸>:…}}` 이다. 서버가 그 칸을 `rules.PRIMARY`·마지막으로 물은 칸 기준으로 `target`/`set` 에 옮긴다.
- `schema/`·`prompt/`·`vectors/` 는 패키지 폴더 밖(`assistant_proto/` 바로 아래)에 있어 **편집 설치(editable path dependency)로만** 읽힌다. 서버·`ml/` 모두 `{ path = "../assistant_proto", editable = true }`.
- 계약 예문 `vectors/forms.v1.jsonl` 한 줄: `{"id": "event.add-1", "prefix": "관리자: ", "utterance": "…", "form": {…}}`.
- 해석기 예문 `vectors/resolve.v1.jsonl` 한 줄: `{"fn": "when"|"weekdays"|"time"|"room", "now": "…", "expr": "…", "expect": {…}|null}`.

해석 규칙(원본은 `assistant_proto/README.md` 표 + `vectors/resolve.v1.jsonl`):
- 주의 시작은 월요일. "이번 주 X요일" / "다음 주 X요일" / "다다음 주 X요일".
- 요일만("금요일", "금")은 오늘 포함 가장 가까운 그 요일.
- "오늘" "내일"·"낼" "모레"·"낼모레". 구어 "이번주"·"담주"(붙여 쓰기)와 "금욜" 도 푼다. "12/3" "12월 3일" "12.3" — 올해, 지났으면 내년. "3일"만 — 이번 달, 지났으면 다음 달.
- 기간 "12/15~19" "12/15~12/19" "15일부터 19일까지" → `range`. 목록 "화, 목" "화목" "11/27, 12/4" → `dates` (요일 목록은 각각 가장 가까운 날).
- "매주 월" "월요일마다" → `weekdays` (날짜별 작업 `event.*` 에서 이것이 나오면 서버가 "매주 반복은 정규 시간표로 등록할까요?"로 되묻는다).
- 정규 시간표(`class.*`)는 `resolve_when` 대신 `resolve_weekdays` 를 쓴다: "월" "월요일" "매주 월" "월수금" "화, 목" → 요일 번호 튜플.
- 시각 "15시" "15:30" "3시 반" "오전 9시" "오후 3시" "정오". 오전·오후 없는 1~8시는 13~20시. 9~12시는 그대로.
- 구간 "3시부터 6시" "3~6시" "15:00-18:00" "3시부터 3시간". 끝만 있는 "6시까지"는 못 풂(None).

---

## 4. HTTP API (`server/app/assistant/router.py`)

모두 `Authorization: Bearer` 관리자(`ManagerUser`) + 건물 범위(`MgrScope`). JSON 키는 snake_case. 날짜 `YYYY-MM-DD`, 시각 ISO 8601.

### 4.1 `GET /api/assistant/model`

```jsonc
// 모델 안내가 아직 없을 때
{"enabled": false}
// 있을 때
{
  "enabled": true,
  "schema_v": 1,
  "runtime": "webllm",                       // 0단계 실험 결과: webllm | transformers | litert | wllama
  "repo": "leemonta9482/esc-assistant-e2b",   // 당분간 wj 개인 계정(spec §17, 2026-11-26)
  "revision": "3f2a…(40자 커밋 해시)",
  "files": [{"name": "…", "size": 123, "sha256": "…"}],
  "system_prompt": "…",                      // assistant_proto.SYSTEM_PROMPT
  "first_prefix": "관리자: ",
  "json_schema": { … },                      // assistant_proto.json_schema()
  "generation": {"temperature": 0, "max_tokens": 256}
}
```
`runtime`·`repo`·`revision`·`files`·`generation` 은 `server/app/assistant/model.json` 에서 읽는다(릴리스 PR 이 이 파일만 바꾼다). 나머지는 `assistant_proto` 에서 채운다.

`model.json` 모양: 처음엔 `{"enabled": false}`. 릴리스 뒤 `{"enabled": true, "runtime": …, "repo": …, "revision": "<40자 커밋 해시>", "files": [{"name", "size", "sha256"}], "generation": {…}}` (`generation` 이 없으면 기본값). 형식이 틀리면 서버가 오류를 낸다.

재시도: 웹은 첫 출력을 JSON 으로 못 읽으면 `temperature 0.3` 으로 한 번 더 생성한다(웹 상수 `RETRY_TEMPERATURE`). 그래도 못 읽으면 `raw_output` 으로 보낸다.

### 4.2 `POST /api/assistant/turns`

요청 `TurnIn`:
```jsonc
{
  "conversation_id": null,      // 첫 턴은 null, 이후 응답으로 받은 값
  "utterance": "803호 이번주 금요일 15시부터 18시까지 특강 예약해줘",   // 1~300자, 버튼 선택 턴은 버튼 라벨
  "form": { … },                // 모델 출력(파싱한 객체)
  "choice": null,               // 선택 버튼 id
  "raw_output": null            // 두 번 시도해도 JSON 으로 못 읽은 모델 출력 원문(≤2000자) — 기록만 하고 error 로 답한다
}                               // form · choice · raw_output 중 정확히 하나 (아니면 422)
```
응답 `TurnOut`:
```jsonc
{
  "conversation_id": "c_6f1e…",
  "kind": "ask",                // ask | preview | answer | error
  "message": "특강 이름은 무엇인가요?",
  "choices": [],                // [{"id": "room:12", "label": "공학관 803"}] — 고를 수 있는 질문일 때
  "next_prefix": "상태: …\n질문: …\n관리자: ",   // 다음 턴 모델 입력 접두어. 대화가 끝났으면 null
  "closed": false,              // true = 대화 끝(취소·조회 답·적용 대기 아님). 다음 턴은 conversation_id null 로
  "preview": null,              // kind == "preview" 일 때 PreviewOut
  "answer": null                // kind == "answer" 일 때 AnswerOut
}
```
- 규격 판이 다른 form(`v` ≠ 1) → **409** `{"detail": "schema_version"}` (프론트는 모델 안내를 다시 받는다).
- 만료·없는 `conversation_id` → 200, `kind: "error"`, `message: "대화가 만료되었습니다. 다시 말씀해 주세요."`, `closed: true`.
- 상한 초과 → 429.

`PreviewOut`:
```jsonc
{
  "preview_id": "p_93ab…",
  "expires_at": "2026-11-25T10:10:00Z",
  "summary": ["+ 11/27(금) 15:00–18:00 특강 \"알고리즘 특강\" (공학관 803)"],
  "blockers": [],               // 하나라도 있으면 적용 불가
  "warnings": ["기존 수업 \"자료구조\"(금 15:00–16:15)와 겹칩니다"],
  "notices": [],
  "rooms": [
    {
      "room_id": 3, "building_id": 1, "label": "공학관 803",
      "added": 1, "removed": 0, "changed": 0,
      "weeks": [
        {
          "week_start": "2026-11-23",       // 그 주 월요일. 정규 시간표만 바뀐 경우 null
          "before": {"slots": [SlotWithRoom], "reservations": [ResvWithRoom], "exams": [ExamWithRoom]},
          "after":  {"slots": [...], "reservations": [...], "exams": [...]},
          "changes": [{"entity": "resv", "key": "r17", "op": "add", "fields": []}]
        }
      ]
    }
  ]
}
```
- `SlotWithRoom`·`ResvWithRoom`·`ExamWithRoom` 은 기존 `server/app/schemas.py`·`web/src/api/types.ts` 의 그 타입 그대로.
- `changes[].key`: 정규 시간표 `"d{day}-{HHMM}"`(예 `d5-1500`), 예약 `"r{id}"`, 시험기간 `"e{id}"`. `op`: `add` | `remove` | `change`. `fields`: `change` 일 때 바뀐 칸 이름(`s_h`·`subject` 등).
- `before` 의 항목은 `remove`·`change`, `after` 의 항목은 `add`·`change` 표시 대상이다(같은 `key`).

`AnswerOut` (조회 답):
```jsonc
{"title": "11/28(금) 13:00~18:00 빈 강의실", "columns": ["강의실", "빈 시간"], "rows": [["공학관 801", "13:00–18:00"]]}
```

### 4.3 `POST /api/assistant/previews/{preview_id}/apply`

- 200 `{"change_id": 41, "outbox_ids": [512, 513]}`
- 409 `{"detail": "stale", "preview": PreviewOut}` — 미리보기 뒤 데이터가 바뀜. 새 미리보기를 보여 준다.
- 410 `{"detail": "expired"}` — 만료(10분) 또는 이미 적용됨.
- 404 `{"detail": "미리보기 없음"}` — 없는 미리보기, 다른 관리자의 미리보기.
- 422 `{"detail": "blocked", "blockers": [...]}` — 막음이 있는 미리보기.

### 4.4 `GET /api/assistant/changes?limit=50`

```jsonc
[{"id": 41, "applied_at": "2026-11-25T01:02:03Z", "user_email": "…", "utterance": "…",
  "summary": ["+ …"], "outbox_ids": [512, 513]}]
```
자기 범위 건물의 변경만(최고 관리자는 학교 전체).

---

## 5. 파일 · 폴더 · 담당

| 경로 | 담당 | 작업지시서 |
|---|---|---|
| `assistant_proto/` | cw | 01 |
| `server/app/assistant/`, `server/app/domain/ops.py`, 새 마이그레이션 | cw (`ops.py` 정리는 wj 리뷰) | 01 |
| `server/app/assistant/model.json` | cw 머지, 값은 wj 릴리스 | 01 만듦, 02 릴리스 때 바꿈 |
| `ml/` | wj | 02 |
| `docs/design/screens/admin-assistant.md`, `components.md`, `admin-master.md` | cw (AI 비서 화면은 wj 시안 · cw 승인, #176) | 03 (Task 0 — 머지 #176) |
| `web/src/admin/assistant/`, `web/src/components/ui/SidebarNav.vue`, `web/src/admin/AdminShell.vue`(창 마운트 — 라우트 없음, #176), `web/src/api/` | wj | 03 |
