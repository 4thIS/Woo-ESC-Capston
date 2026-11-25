# 관리자 AI 비서 — 양식 규격 + 서버 백엔드 구현 계획 (plan 01, cw)

<!-- 배치: docs/plans/2026-11-25-ai-assistant-01-proto-backend.md -->
<!-- writing-plans 스킬로 작성. spec을 "어떻게"로 옮긴 작업지시서. -->

- 생성일시: 2026-11-25
- 기준 spec: `docs/specs/2026-11-25-admin-ai-assistant-design.md`
- 공통 부록: `docs/plans/2026-11-25-ai-assistant-00-interfaces.md` (이름·모양은 부록 그대로)
- 담당: cw @ssenu. `server/app/domain/ops.py` 정리와 `daily.py` 한 줄은 wj 리뷰.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 AI 비서의 양식 규격 패키지 `assistant_proto/` 와, 그 양식을 받아 되묻기 → 전·후 미리보기 → 적용까지 하는 서버 `server/app/assistant/` 를 만든다.

**Architecture:** `assistant_proto/` 는 `lora_proto/` 처럼 DB·네트워크 없는 단일 진실원(양식 검증·정규 직렬화·날짜/시각 해석기·대화 규칙·프롬프트·예문)이다. 서버는 기존 관리자 쓰기 코드에서 "커밋하지 않는 쓰기" 를 `app/domain/ops.py` 로 떼어 내, 미리보기(실행 → 읽기 → rollback)와 적용(실행 → 커밋 → notify)이 **같은 함수**를 쓰게 한다. 대화 상태·미리보기·변경 기록은 새 표 4개에 둔다.

**Tech Stack:** Python 3.12 · uv · FastAPI · SQLAlchemy 2 · Alembic · pytest · ruff (서버·`assistant_proto` 공통)

## Global Constraints

- 양식·프롬프트·API 의 이름과 JSON 키는 공통 부록 §1~§4 그대로 쓴다 (`intent` 18개, `target`/`set`, 정규 직렬화 키 순서, `TurnIn`/`TurnOut`/`PreviewOut`/`AnswerOut`, `changes[].key` 규칙 `d{day}-{HHMM}`·`r{id}`·`e{id}`).
- `assistant_proto/` 는 PM 전담 계약이다 — **단독 PR 로 먼저 머지**(lockstep). 그 규격을 쓰는 서버 코드는 다음 PR.
- `lora_proto/` 는 바꾸지 않는다. 노드·모뎀Pi·펌웨어는 바뀌지 않는다.
- `server/app/lora_service/` 는 건드리지 않는다 — `api.enqueue_*(…, session=s)` 와 `api.notify` 만 부른다. outbox 를 직접 INSERT 하지 않는다.
- 기존 API 의 요청·응답은 바뀌지 않는다(새 경로만 — additive). 쓰기 정리 뒤 **기존 테스트는 고치지 않고 그대로 통과**해야 한다.
- 채번(`_free_id`)·같은 방 검사(`_existing_same_room`)·`ID_MAX`·`_ID_LOCK` 은 `app/domain/router.py` 에 그대로 둔다 — `tests/test_admin_ids.py` 가 그 모듈 속성을 바꿔 끼운다.
- 새 표는 마이그레이션 prefix `web_`, 쓰는 코드보다 먼저(같은 PR 안에서도 앞 커밋).
- 새 필수 env 없음 (`main` 머지 = 홈서버 반영, `esc-autodeploy`).
- 워커 1개 — 대화·미리보기 상태는 DB 에 둔다(프로세스 메모리 금지). 시각은 DB 에 naive UTC, 판정은 KST(`app.domain.clock`).
- 모든 새 경로는 `ManagerUser` + `MgrScope`(건물 범위). 범위 밖 방은 해석 단계에서 없는 것과 같다.
- 관리자 문장은 외부 서비스로 보내지 않는다. 턴 기록은 180일 뒤 지운다.
- 비밀값·`.env` 커밋 금지, `git push --force`·`git reset --hard` 금지. 커밋 메시지에 attribution 줄을 넣지 않는다.
- 커밋 scope: `feat(proto)`(assistant_proto — 계약), `feat(server)`, `refactor(server)`, `test(server)`, `chore(infra)`, `docs`.
- import 정렬·줄 나눔은 ruff 가 정한다 — 계획의 코드와 모양이 다르면 `uv run ruff check --fix . && uv run ruff format .` 결과를 따른다(동작은 같다). 테스트 기대값은 바꾸지 않는다.

## PR 경계

| PR | 브랜치 | Task | 머지 조건 |
|---|---|---|---|
| **A** `feat(proto): assistant_proto v1` | `feature/assistant-proto` | 1~4 | **단독, 가장 먼저** (lockstep). CI `assistant_proto` job 녹색 |
| **B** `feat(server): 관리자 AI 비서 백엔드` | `feature/assistant-server` (A 머지 후 main 에서) | 5~17 | CI `server`·`docker` 녹색. `ops.py`·`daily.py` 는 wj 리뷰 |
| **C** `docs: 역할 표 — mh 제외 · AI 비서 영역 · 홈서버 배포` | `docs/assistant-roles` | 18 | 언제든(A 와 독립). 웹 계획(03) Task 0 의 화면 스펙 PR 과는 별개 |

## 파일 지도

```
assistant_proto/                      (새, PR A)
├── pyproject.toml · uv.lock · README.md
├── schema/form.v1.json               양식 JSON Schema
├── prompt/system.v1.txt              시스템 지시문
├── vectors/forms.v1.jsonl            계약 예문 (평가·테스트 전용)
├── vectors/resolve.v1.jsonl          해석기 예문
├── assistant_proto/__init__.py       공개 API 모음
├── assistant_proto/form.py           parse_form · form_to_dict · canonical_json · json_schema · type_code
├── assistant_proto/resolve.py        resolve_when · resolve_weekdays · resolve_time · normalize_room
├── assistant_proto/prompt.py         SYSTEM_PROMPT · FIRST_PREFIX · render_prefix
├── assistant_proto/rules.py          PRIMARY · missing · question · state_items (대화 규칙 — 서버·ml 공용)
└── tests/test_form.py · test_resolve.py · test_prompt.py · test_rules.py · test_forms_vectors.py

server/                               (PR B)
├── pyproject.toml · uv.lock          assistant-proto 경로 의존성
├── Dockerfile · ../.dockerignore      assistant_proto/ 를 이미지에
├── alembic/env.py                    app.assistant.models import
├── alembic/versions/web_assistant_a7c3e91d5f20.py
├── app/domain/ops.py                 커밋하지 않는 쓰기 (새)
├── app/domain/router.py              ops 를 쓰게 정리 (동작 불변)
├── app/domain/daily.py               assistant 정리 단계 한 줄
├── app/main.py                       라우터 등록
└── app/assistant/
    ├── __init__.py
    ├── models.py      표 4개
    ├── schemas.py     TurnIn · TurnOut · PreviewOut · AnswerOut · ChangeOut
    ├── manifest.py    model.json → GET /model
    ├── model.json     {"enabled": false} 로 시작 (릴리스 PR 이 바꿈)
    ├── rooms.py       강의실 표현 → 방 (DB, 범위)
    ├── dialog.py      대화 상태 · 한 턴 진행
    ├── changes.py     대상 찾기 · 확정 변경 목록 · 요약 · 경고
    ├── preview.py     run_ops · fingerprint · 미리보기 · 적용
    ├── answers.py     조회 답
    ├── service.py     턴 처리 · 저장 · 기록 · 변경 목록
    ├── prune.py       오래된 기록 정리
    └── router.py      /api/assistant/*
server/tests/
├── assistant_util.py (픽스처 도우미, 수집 안 됨)
├── test_assistant_proto_dep.py · test_domain_ops.py · test_assistant_migration.py
├── test_assistant_rooms.py · test_assistant_dialog.py · test_assistant_advance.py
├── test_assistant_preview.py · test_assistant_apply.py · test_assistant_answers.py
├── test_assistant_api.py · test_assistant_prune.py · test_assistant_guarantees.py
```

---

## PR A — `assistant_proto/` (계약, 단독 먼저)

```bash
git switch main && git pull --ff-only && git switch -c feature/assistant-proto
```

### Task 1: 패키지 뼈대 + 양식 검증·정규 직렬화

**Files:**
- Create: `assistant_proto/pyproject.toml`, `assistant_proto/schema/form.v1.json`, `assistant_proto/assistant_proto/__init__.py`, `assistant_proto/assistant_proto/form.py`
- Test: `assistant_proto/tests/__init__.py`(빈 파일), `assistant_proto/tests/test_form.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION`, `INTENTS`, `TYPE_LABELS`, `FIELD_ORDER`, `Fields`, `Form`, `FormError`, `parse_form(text_or_obj) -> Form`, `form_to_dict(form) -> dict`, `canonical_json(form|dict) -> str`, `json_schema() -> dict`, `type_code(label) -> int` (부록 §3)

- [ ] **Step 1: pyproject + 빈 패키지**

`assistant_proto/pyproject.toml`:
```toml
[project]
name = "assistant-proto"
version = "1.0.0"
description = "Woo-ESC-Capston 관리자 AI 비서 양식 규격 v1 — 양식 검증·해석기·대화 규칙·프롬프트·예문 (단일 진실원)"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.7", "jsonschema>=4.23"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["assistant_proto"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`assistant_proto/tests/__init__.py`: 빈 파일.

- [ ] **Step 2: 실패하는 테스트**

`assistant_proto/tests/test_form.py`:
```python
import json

import jsonschema
import pytest

from assistant_proto import (
    FIELD_ORDER,
    INTENTS,
    SCHEMA_VERSION,
    TYPE_LABELS,
    Fields,
    FormError,
    canonical_json,
    form_to_dict,
    json_schema,
    parse_form,
    type_code,
)

GOOD = {
    "v": 1,
    "intent": "event.add",
    "target": {},
    "set": {"rooms": ["803"], "when": "이번 주 금요일", "time": "15시부터 18시까지", "type": "특강"},
}


def test_constants():
    assert SCHEMA_VERSION == 1
    assert len(INTENTS) == 18 and len(set(INTENTS)) == 18
    assert INTENTS[0] == "event.add" and INTENTS[-3:] == ("fill", "cancel", "unknown")
    assert TYPE_LABELS == ("수업", "시험", "휴강", "빈강의실", "특강", "대여")
    assert FIELD_ORDER == (
        "rooms", "when", "time", "type", "subject", "professor", "reason", "requester",
    )


def test_type_code():
    assert [type_code(x) for x in TYPE_LABELS] == [1, 2, 3, 4, 5, 6]
    with pytest.raises(ValueError):
        type_code("보강")


def test_parse_from_str_and_dict():
    f = parse_form(json.dumps(GOOD, ensure_ascii=False))
    assert f == parse_form(GOOD)
    assert f.intent == "event.add" and f.target == Fields()
    assert f.set.rooms == ("803",) and f.set.type == "특강" and f.set.subject is None


def test_form_to_dict_roundtrip():
    assert form_to_dict(parse_form(GOOD)) == GOOD


def test_canonical_json_orders_keys():
    shuffled = {
        "set": {"type": "특강", "time": "15시부터 18시까지", "when": "이번 주 금요일", "rooms": ["803"]},
        "target": {},
        "intent": "event.add",
        "v": 1,
    }
    want = (
        '{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"],'
        '"when":"이번 주 금요일","time":"15시부터 18시까지","type":"특강"}}'
    )
    assert canonical_json(shuffled) == want
    assert canonical_json(parse_form(GOOD)) == want


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        [],
        {**GOOD, "v": 2},
        {**GOOD, "v": True},
        {**GOOD, "intent": "event.add2"},
        {k: v for k, v in GOOD.items() if k != "target"},
        {**GOOD, "extra": 1},
        {**GOOD, "set": {"room": ["803"]}},
        {**GOOD, "set": {"rooms": []}},
        {**GOOD, "set": {"rooms": ["8" * 21]}},
        {**GOOD, "set": {"rooms": "803"}},
        {**GOOD, "set": {"type": "보강"}},
        {**GOOD, "set": {"when": ""}},
        {**GOOD, "set": {"subject": None}},
        {**GOOD, "set": {"reason": "가" * 101}},
        {**GOOD, "target": []},
    ],
)
def test_parse_rejects(bad):
    with pytest.raises(FormError):
        parse_form(bad)


def test_json_schema_matches_constants():
    sc = json_schema()
    assert sc["properties"]["v"] == {"const": 1}
    assert tuple(sc["properties"]["intent"]["enum"]) == INTENTS
    f = sc["$defs"]["fields"]
    assert tuple(f["properties"]) == FIELD_ORDER
    assert tuple(f["properties"]["type"]["enum"]) == TYPE_LABELS
    assert sc["additionalProperties"] is False and f["additionalProperties"] is False


def test_json_schema_agrees_with_parser():
    v = jsonschema.Draft202012Validator(json_schema())
    assert not list(v.iter_errors(GOOD))
    for bad in (
        {**GOOD, "v": 2},
        {**GOOD, "set": {"type": "보강"}},
        {**GOOD, "set": {"rooms": []}},
        {**GOOD, "extra": 1},
        {**GOOD, "set": {"when": ""}},
    ):
        assert list(v.iter_errors(bad)), bad
```

Run: `cd assistant_proto && uv lock && uv sync && uv run pytest tests/test_form.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'assistant_proto'` 또는 import 오류.

- [ ] **Step 3: JSON Schema**

`assistant_proto/schema/form.v1.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://esc.ssenu.cloud/assistant/form.v1.json",
  "title": "ESC 관리자 AI 비서 양식 v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["v", "intent", "target", "set"],
  "properties": {
    "v": {"const": 1},
    "intent": {
      "enum": [
        "event.add", "event.change", "event.remove",
        "exam.add", "exam.change", "exam.remove",
        "class.add", "class.change", "class.remove",
        "request.approve", "request.reject",
        "ask.free_rooms", "ask.schedule", "ask.requests", "ask.node",
        "fill", "cancel", "unknown"
      ]
    },
    "target": {"$ref": "#/$defs/fields"},
    "set": {"$ref": "#/$defs/fields"}
  },
  "$defs": {
    "fields": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "rooms": {
          "type": "array",
          "minItems": 1,
          "maxItems": 30,
          "items": {"type": "string", "minLength": 1, "maxLength": 20}
        },
        "when": {"type": "string", "minLength": 1, "maxLength": 40},
        "time": {"type": "string", "minLength": 1, "maxLength": 40},
        "type": {"enum": ["수업", "시험", "휴강", "빈강의실", "특강", "대여"]},
        "subject": {"type": "string", "minLength": 1, "maxLength": 40},
        "professor": {"type": "string", "minLength": 1, "maxLength": 20},
        "reason": {"type": "string", "minLength": 1, "maxLength": 100},
        "requester": {"type": "string", "minLength": 1, "maxLength": 20}
      }
    }
  }
}
```

- [ ] **Step 4: 구현**

`assistant_proto/assistant_proto/form.py`:
```python
"""양식(form) v1 — 모델 출력의 모양 (spec §3, 공통 부록 §1).

schema/form.v1.json 과 같은 규칙을 의존성 없이 검사한다 — 서버·ml 이 jsonschema 없이 쓰게.
두 규칙이 같은지는 tests/test_form.py 가 본다."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SCHEMA_VERSION = 1
INTENTS: tuple[str, ...] = (
    "event.add",
    "event.change",
    "event.remove",
    "exam.add",
    "exam.change",
    "exam.remove",
    "class.add",
    "class.change",
    "class.remove",
    "request.approve",
    "request.reject",
    "ask.free_rooms",
    "ask.schedule",
    "ask.requests",
    "ask.node",
    "fill",
    "cancel",
    "unknown",
)
TYPE_LABELS: tuple[str, ...] = ("수업", "시험", "휴강", "빈강의실", "특강", "대여")  # = 서버 type 1~6
FIELD_ORDER: tuple[str, ...] = (
    "rooms",
    "when",
    "time",
    "type",
    "subject",
    "professor",
    "reason",
    "requester",
)
TEXT_MAX = {"when": 40, "time": 40, "subject": 40, "professor": 20, "reason": 100, "requester": 20}
ROOMS_MAX, ROOM_LEN_MAX = 30, 20
# schema/·prompt/·vectors/ 는 패키지 밖(assistant_proto/ 바로 아래)에 있다 — 서버·ml 은 편집 설치(path 의존)
ROOT = Path(__file__).resolve().parents[1]


class FormError(ValueError):
    """규격 위반."""


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


@cache
def _schema_text() -> str:
    return (ROOT / "schema" / "form.v1.json").read_text(encoding="utf-8")


def json_schema() -> dict:
    return json.loads(_schema_text())


def type_code(label: str) -> int:
    try:
        return TYPE_LABELS.index(label) + 1
    except ValueError:
        raise ValueError(f"모르는 유형 {label!r}") from None


def _fields(obj: object, where: str) -> Fields:
    if not isinstance(obj, dict):
        raise FormError(f"{where} 는 객체")
    extra = sorted(set(obj) - set(FIELD_ORDER))
    if extra:
        raise FormError(f"{where} 에 모르는 칸 {extra}")
    kw: dict = {}
    for k, v in obj.items():
        if k == "rooms":
            ok = (
                isinstance(v, list)
                and 1 <= len(v) <= ROOMS_MAX
                and all(isinstance(x, str) and 1 <= len(x) <= ROOM_LEN_MAX for x in v)
            )
            if not ok:
                raise FormError(f"{where}.rooms 는 1~{ROOMS_MAX}개, 각 1~{ROOM_LEN_MAX}자 문자열")
            kw[k] = tuple(v)
        elif k == "type":
            if v not in TYPE_LABELS:
                raise FormError(f"{where}.type 은 {'·'.join(TYPE_LABELS)} 중 하나")
            kw[k] = v
        else:
            if not isinstance(v, str) or not 1 <= len(v) <= TEXT_MAX[k]:
                raise FormError(f"{where}.{k} 는 1~{TEXT_MAX[k]}자 문자열")
            kw[k] = v
    return Fields(**kw)


def parse_form(text_or_obj: str | dict) -> Form:
    obj = text_or_obj
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError as e:
            raise FormError(f"JSON 이 아님: {e.msg}") from e
    if not isinstance(obj, dict):
        raise FormError("양식은 객체")
    if set(obj) != {"v", "intent", "target", "set"}:
        raise FormError("키는 v·intent·target·set 넷")
    v = obj["v"]
    if isinstance(v, bool) or v != SCHEMA_VERSION:
        raise FormError(f"v 는 {SCHEMA_VERSION}")
    if not isinstance(obj["intent"], str) or obj["intent"] not in INTENTS:
        raise FormError(f"모르는 intent {obj['intent']!r}")
    return Form(
        SCHEMA_VERSION, obj["intent"], _fields(obj["target"], "target"), _fields(obj["set"], "set")
    )


def _fields_dict(f: Fields) -> dict:
    out: dict = {}
    for k in FIELD_ORDER:
        v = getattr(f, k)
        if v is not None:
            out[k] = list(v) if k == "rooms" else v
    return out


def form_to_dict(form: Form) -> dict:
    """없는 칸은 키를 뺀다. 키 순서 = 정규 순서."""
    return {
        "v": form.v,
        "intent": form.intent,
        "target": _fields_dict(form.target),
        "set": _fields_dict(form.set),
    }


def canonical_json(form: Form | dict) -> str:
    """모델 출력·학습 정답의 정규형 (부록 §1.3). dict 를 주면 먼저 검증한다."""
    f = form if isinstance(form, Form) else parse_form(form)
    return json.dumps(form_to_dict(f), ensure_ascii=False, separators=(",", ":"))
```

`assistant_proto/assistant_proto/__init__.py`:
```python
"""관리자 AI 비서 양식 규격 v1 — 단일 진실원 (spec 2026-11-25 §3, 공통 부록 §1~§3).
서버(server/app/assistant)·학습(ml/)이 경로 의존성으로 쓴다. DB·네트워크 없음."""

from assistant_proto.form import (
    FIELD_ORDER,
    INTENTS,
    SCHEMA_VERSION,
    TYPE_LABELS,
    Fields,
    Form,
    FormError,
    canonical_json,
    form_to_dict,
    json_schema,
    parse_form,
    type_code,
)

__all__ = [
    "FIELD_ORDER",
    "INTENTS",
    "SCHEMA_VERSION",
    "TYPE_LABELS",
    "Fields",
    "Form",
    "FormError",
    "canonical_json",
    "form_to_dict",
    "json_schema",
    "parse_form",
    "type_code",
]
```

- [ ] **Step 5: 통과 + 커밋**

Run: `cd assistant_proto && uv run pytest tests/test_form.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (`ruff format --check` 가 실패하면 `uv run ruff format .` 후 다시).

```bash
git add assistant_proto/pyproject.toml assistant_proto/uv.lock assistant_proto/schema/form.v1.json \
  assistant_proto/assistant_proto/__init__.py assistant_proto/assistant_proto/form.py \
  assistant_proto/tests/__init__.py assistant_proto/tests/test_form.py
git commit -m "feat(proto): assistant_proto 뼈대 — 양식 v1 JSON Schema·검증·정규 직렬화"
```

---

### Task 2: 해석기 — 날짜·요일·시각·강의실 표현

**Files:**
- Create: `assistant_proto/assistant_proto/resolve.py`, `assistant_proto/vectors/resolve.v1.jsonl`
- Modify: `assistant_proto/assistant_proto/__init__.py`
- Test: `assistant_proto/tests/test_resolve.py`

**Interfaces:**
- Consumes: 없음
- Produces: `When(kind, dates, start, end, weekdays)`, `TimeSpan(start, end)`, `resolve_when(expr, now) -> When | None`, `resolve_weekdays(expr) -> tuple[int, ...] | None`, `resolve_time(expr) -> TimeSpan | None`, `normalize_room(expr) -> str` (부록 §3). `now` 는 `.date()` 만 쓴다 — aware·naive 둘 다 된다.

- [ ] **Step 1: 예문 파일 (해석 규칙의 원본)**

기준 시각은 전부 `2026-11-25T10:00:00+09:00` (수요일, 그 주 월요일 = 11/23).

`assistant_proto/vectors/resolve.v1.jsonl`:
```jsonl
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"오늘","expect":{"kind":"dates","dates":["2026-11-25"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"내일","expect":{"kind":"dates","dates":["2026-11-26"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"모레","expect":{"kind":"dates","dates":["2026-11-27"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"내일모레","expect":{"kind":"dates","dates":["2026-11-27"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"이번 주 금요일","expect":{"kind":"dates","dates":["2026-11-27"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"이번주 월요일","expect":{"kind":"dates","dates":["2026-11-23"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"금주 목","expect":{"kind":"dates","dates":["2026-11-26"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"다음 주 화요일","expect":{"kind":"dates","dates":["2026-12-01"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"담주 금","expect":{"kind":"dates","dates":["2026-12-04"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"이번주 금욜","expect":{"kind":"dates","dates":["2026-11-27"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"낼","expect":{"kind":"dates","dates":["2026-11-26"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"다다음 주 수","expect":{"kind":"dates","dates":["2026-12-09"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"지난주 금요일","expect":{"kind":"dates","dates":["2026-11-20"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"다음 주 화, 목","expect":{"kind":"dates","dates":["2026-12-01","2026-12-03"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"금요일","expect":{"kind":"dates","dates":["2026-11-27"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"수요일","expect":{"kind":"dates","dates":["2026-11-25"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"화","expect":{"kind":"dates","dates":["2026-12-01"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"화목","expect":{"kind":"dates","dates":["2026-11-26","2026-12-01"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12/3","expect":{"kind":"dates","dates":["2026-12-03"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12월 3일","expect":{"kind":"dates","dates":["2026-12-03"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12.3","expect":{"kind":"dates","dates":["2026-12-03"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"1/5","expect":{"kind":"dates","dates":["2027-01-05"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"11/20","expect":{"kind":"dates","dates":["2027-11-20"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"2026-12-07","expect":{"kind":"dates","dates":["2026-12-07"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"3일","expect":{"kind":"dates","dates":["2026-12-03"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"30일","expect":{"kind":"dates","dates":["2026-11-30"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"11/27, 12/4","expect":{"kind":"dates","dates":["2026-11-27","2026-12-04"]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12/15~19","expect":{"kind":"range","start":"2026-12-15","end":"2026-12-19"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12/15~12/19","expect":{"kind":"range","start":"2026-12-15","end":"2026-12-19"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12/15-19","expect":{"kind":"range","start":"2026-12-15","end":"2026-12-19"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"15일부터 19일까지","expect":{"kind":"range","start":"2026-12-15","end":"2026-12-19"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12월 14일부터 18일까지","expect":{"kind":"range","start":"2026-12-14","end":"2026-12-18"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12/28~1/3","expect":{"kind":"range","start":"2026-12-28","end":"2027-01-03"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"이번 주 월~금","expect":{"kind":"range","start":"2026-11-23","end":"2026-11-27"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"다음 주 월요일부터 금요일까지","expect":{"kind":"range","start":"2026-11-30","end":"2026-12-04"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"이번 주","expect":{"kind":"range","start":"2026-11-23","end":"2026-11-29"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"다음 주","expect":{"kind":"range","start":"2026-11-30","end":"2026-12-06"}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"매주 월","expect":{"kind":"weekdays","weekdays":[1]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"월요일마다","expect":{"kind":"weekdays","weekdays":[1]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"매주 월수금","expect":{"kind":"weekdays","weekdays":[1,3,5]}}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"언젠가","expect":null}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"2/30","expect":null}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":"12/19~12/15","expect":null}
{"fn":"when","now":"2026-11-25T10:00:00+09:00","expr":" ","expect":null}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"월","expect":[1]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"월요일","expect":[1]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"매주 월","expect":[1]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"월수금","expect":[1,3,5]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"화, 목","expect":[2,4]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"월~금","expect":[1,2,3,4,5]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"매주 수요일","expect":[3]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"금요일마다","expect":[5]}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"12/3","expect":null}
{"fn":"weekdays","now":"2026-11-25T10:00:00+09:00","expr":"주말","expect":null}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"15시부터 18시까지","expect":{"start":"15:00","end":"18:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"3시부터 6시","expect":{"start":"15:00","end":"18:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"3~6시","expect":{"start":"15:00","end":"18:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"15:00-18:00","expect":{"start":"15:00","end":"18:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"오전 9시부터 12시","expect":{"start":"09:00","end":"12:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"9시~10시 반","expect":{"start":"09:00","end":"10:30"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"오후 2시 30분부터 4시","expect":{"start":"14:30","end":"16:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"3시부터 3시간","expect":{"start":"15:00","end":"18:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"1시부터 2시간 반","expect":{"start":"13:00","end":"15:30"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"정오부터 1시","expect":{"start":"12:00","end":"13:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"10시부터 1시까지","expect":{"start":"10:00","end":"13:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"오후 3시부터 4시 15분","expect":{"start":"15:00","end":"16:15"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"오후 4시부터 6시","expect":{"start":"16:00","end":"18:00"}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"3시 반","expect":{"start":"15:30","end":null}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"오후 3시","expect":{"start":"15:00","end":null}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"오전 10시","expect":{"start":"10:00","end":null}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"16시","expect":{"start":"16:00","end":null}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"16시로","expect":{"start":"16:00","end":null}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"9시","expect":{"start":"09:00","end":null}}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"6시까지","expect":null}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"15시~14시","expect":null}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"몇 시","expect":null}
{"fn":"time","now":"2026-11-25T10:00:00+09:00","expr":"25시","expect":null}
{"fn":"room","now":"2026-11-25T10:00:00+09:00","expr":"803호","expect":"803"}
{"fn":"room","now":"2026-11-25T10:00:00+09:00","expr":" 공학관  803 호 ","expect":"공학관 803"}
{"fn":"room","now":"2026-11-25T10:00:00+09:00","expr":"801호~805호","expect":"801~805"}
{"fn":"room","now":"2026-11-25T10:00:00+09:00","expr":"801 - 805","expect":"801-805"}
{"fn":"room","now":"2026-11-25T10:00:00+09:00","expr":"8 층 전체","expect":"8층 전체"}
{"fn":"room","now":"2026-11-25T10:00:00+09:00","expr":"803","expect":"803"}
{"fn":"room","now":"2026-11-25T10:00:00+09:00","expr":"E동 301호","expect":"E동 301"}
```

- [ ] **Step 2: 실패하는 테스트**

`assistant_proto/tests/test_resolve.py`:
```python
import json
from datetime import datetime
from pathlib import Path

import pytest

from assistant_proto import normalize_room, resolve_time, resolve_weekdays, resolve_when

VEC = Path(__file__).resolve().parents[1] / "vectors" / "resolve.v1.jsonl"
ROWS = [json.loads(x) for x in VEC.read_text(encoding="utf-8").splitlines() if x.strip()]


def _when_json(w):
    if w is None:
        return None
    if w.kind == "dates":
        return {"kind": "dates", "dates": [d.isoformat() for d in w.dates]}
    if w.kind == "range":
        return {"kind": "range", "start": w.start.isoformat(), "end": w.end.isoformat()}
    return {"kind": "weekdays", "weekdays": list(w.weekdays)}


def _time_json(t):
    if t is None:
        return None
    return {"start": t.start.strftime("%H:%M"), "end": t.end.strftime("%H:%M") if t.end else None}


@pytest.mark.parametrize("v", ROWS, ids=lambda v: f"{v['fn']}:{v['expr']}")
def test_vector(v):
    now = datetime.fromisoformat(v["now"])
    if v["fn"] == "when":
        assert _when_json(resolve_when(v["expr"], now)) == v["expect"]
    elif v["fn"] == "weekdays":
        got = resolve_weekdays(v["expr"])
        assert (list(got) if got else None) == v["expect"]
    elif v["fn"] == "time":
        assert _time_json(resolve_time(v["expr"])) == v["expect"]
    else:
        assert normalize_room(v["expr"]) == v["expect"]


def test_every_function_has_vectors():
    assert {v["fn"] for v in ROWS} == {"when", "weekdays", "time", "room"}


def test_naive_now_works_too():
    # 서버는 KST naive 시각을 넘긴다 — .date() 만 쓰므로 같다
    assert resolve_when("내일", datetime(2026, 11, 25, 10, 0)).dates[0].isoformat() == "2026-11-26"
```

Run: `cd assistant_proto && uv run pytest tests/test_resolve.py -q`
Expected: FAIL — `ImportError: cannot import name 'normalize_room'`.

- [ ] **Step 3: 구현**

`assistant_proto/assistant_proto/resolve.py`:
```python
"""표현 → 값 (공통 부록 §3). 순수 함수 — DB·네트워크 없음. 못 풀면 None (추측하지 않는다).

규칙의 원본은 README 표와 vectors/resolve.v1.jsonl — 바꾸면 셋을 함께 고친다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

WEEKDAYS = "월화수목금토일"
_WEEK_WORDS = {"이번주": 0, "금주": 0, "다음주": 1, "담주": 1, "다다음주": 2, "지난주": -1, "저번주": -1}
_DAY_WORDS = {"오늘": 0, "내일": 1, "낼": 1, "모레": 2, "내일모레": 2, "낼모레": 2, "글피": 3}
_PREFIX = re.compile(r"^(다다음주|이번주|금주|다음주|담주|지난주|저번주)")
_MD = re.compile(r"^(?:(\d{4})[-./년])?(\d{1,2})(?:[-/.]|월)(\d{1,2})일?$")
_DAY = re.compile(r"^(\d{1,2})일$")
_ISO = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_LIST_SEP = re.compile(r",|、|와|과|랑|하고|및")
_CLOCK = re.compile(r"^(오전|오후|아침|낮|저녁|밤)?(\d{1,2})(?::(\d{2})|시(?:(\d{1,2})분|반)?)?$")
_DUR = re.compile(r"^(?:(\d{1,2})시간(반)?|(\d{1,3})분)$")
_TIME_SEPS = ("부터", "에서", "~", "-")


@dataclass(frozen=True)
class When:
    kind: Literal["dates", "range", "weekdays"]
    dates: tuple[date, ...] = ()
    start: date | None = None
    end: date | None = None
    weekdays: tuple[int, ...] = ()


@dataclass(frozen=True)
class TimeSpan:
    start: time
    end: time | None


def _compact(expr: str) -> str:
    return re.sub(r"\s+", "", expr)


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _next_month(d: date) -> tuple[int, int]:
    return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)


def _monday(today: date, offset: int) -> date:
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


def _weekday_dates(tok: str, today: date, offset: int | None) -> list[date] | None:
    """'금' '금요일' '화목' → 날짜들. offset 이 있으면 그 주, 없으면 오늘 포함 가장 가까운 그 요일."""
    chars = tok.replace("요일", "").replace("욜", "")  # 구어 "금욜"
    if not chars or any(c not in WEEKDAYS for c in chars):
        return None
    out = []
    for c in chars:
        wd = WEEKDAYS.index(c)  # 0 = 월
        if offset is None:
            out.append(today + timedelta(days=(wd - today.weekday()) % 7))
        else:
            out.append(_monday(today, offset) + timedelta(days=wd))
    return out


def _one_date(tok: str, today: date) -> date | None:
    if tok in _DAY_WORDS:
        return today + timedelta(days=_DAY_WORDS[tok])
    if m := _MD.match(tok):
        y, mo, d = m.groups()
        if y:
            return _mk(int(y), int(mo), int(d))
        got = _mk(today.year, int(mo), int(d))
        if got is None:
            return None
        return got if got >= today else _mk(today.year + 1, int(mo), int(d))
    if m := _DAY.match(tok):
        d = int(m.group(1))
        got = _mk(today.year, today.month, d)
        if got is not None and got >= today:
            return got
        return _mk(*_next_month(today), d)
    return None


def _range_end(tok: str, start: date) -> date | None:
    """기간의 끝 — '19' '19일' 은 시작과 같은 달(앞이면 다음 달), '1/3' 은 시작 뒤 가장 가까운 그 날."""
    if m := re.fullmatch(r"(\d{1,2})일?", tok):
        d = int(m.group(1))
        got = _mk(start.year, start.month, d)
        if got is not None and got >= start:
            return got
        return _mk(*_next_month(start), d)
    if m := _MD.match(tok):
        y, mo, d = m.groups()
        if y:
            return _mk(int(y), int(mo), int(d))
        got = _mk(start.year, int(mo), int(d))
        if got is None:
            return None
        return got if got >= start else _mk(start.year + 1, int(mo), int(d))
    return None


def _split_range(t: str) -> tuple[str, str] | None:
    if "부터" in t:
        a, b = t.split("부터", 1)
    elif "~" in t:
        a, b = t.split("~", 1)
    elif "-" in t and not _ISO.match(t):
        a, b = t.split("-", 1)
    else:
        return None
    b = b.removesuffix("까지")
    return (a, b) if a and b else None


def resolve_when(expr: str, now: datetime) -> When | None:
    today = now.date()
    t = _compact(expr)
    if not t:
        return None
    if t.startswith("매주") or t.endswith("마다"):
        wds = resolve_weekdays(expr)
        return When("weekdays", weekdays=wds) if wds else None
    offset = None
    if m := _PREFIX.match(t):
        offset, t = _WEEK_WORDS[m.group(1)], t[m.end() :]
        if not t:  # "이번 주" 만 — 그 주 월~일
            mon = _monday(today, offset)
            return When("range", start=mon, end=mon + timedelta(days=6))
    if rng := _split_range(t):
        a, b = rng
        if offset is not None:  # "이번 주 월~금"
            da, db = _weekday_dates(a, today, offset), _weekday_dates(b, today, offset)
            if not da or not db or len(da) != 1 or len(db) != 1 or db[0] < da[0]:
                return None
            return When("range", start=da[0], end=db[0])
        start = _one_date(a, today)
        end = _range_end(b, start) if start else None
        if start is None or end is None or end < start:
            return None
        return When("range", start=start, end=end)
    dates: list[date] = []
    for tok in (x for x in _LIST_SEP.split(t) if x):
        if (ws := _weekday_dates(tok, today, offset)) is not None:
            dates += ws
            continue
        if offset is not None:
            return None
        if (d := _one_date(tok, today)) is None:
            return None
        dates.append(d)
    return When("dates", dates=tuple(sorted(set(dates)))) if dates else None


def resolve_weekdays(expr: str) -> tuple[int, ...] | None:
    t = _compact(expr).removeprefix("매주").removesuffix("마다")
    if m := re.fullmatch(r"([월화수목금토일])(?:요일)?~([월화수목금토일])(?:요일)?", t):
        a, b = WEEKDAYS.index(m.group(1)) + 1, WEEKDAYS.index(m.group(2)) + 1
        return tuple(range(a, b + 1)) if a <= b else None
    t = _LIST_SEP.sub("", t).replace("요일", "")
    if not t or any(c not in WEEKDAYS for c in t):
        return None
    return tuple(sorted({WEEKDAYS.index(c) + 1 for c in t}))


def _clock(tok: str, *, bare_ok: bool) -> time | None:
    """'15시' '3시 반' '오후 2시 30분' '15:30' '정오'. 오전·오후 없는 1~8시는 오후(수업 시간대)."""
    if tok in ("정오", "낮12시"):
        return time(12, 0)
    m = _CLOCK.match(tok)
    if not m:
        return None
    ap, hh, mm1, mm2 = m.groups()
    if not bare_ok and ":" not in tok and "시" not in tok:
        return None
    h, mi = int(hh), int(mm1 or mm2 or 0)
    if tok.endswith("반"):
        mi = 30
    if h > 23 or mi > 59:
        return None
    if ap in ("오후", "저녁", "밤") and h < 12:
        h += 12
    elif ap in ("오전", "아침") and h == 12:
        h = 0
    elif ap in (None, "낮") and 1 <= h <= 8:
        h += 12
    return time(h, mi)


def resolve_time(expr: str) -> TimeSpan | None:
    t = re.sub(r"(으로|로)$", "", _compact(expr))
    if not t:
        return None
    seps = [x for x in _TIME_SEPS if x in t]
    if not seps:
        if t.endswith("까지"):  # 끝만 말함 — 못 푼다
            return None
        start = _clock(t, bare_ok=False)
        return TimeSpan(start, None) if start else None
    a, b = t.split(seps[0], 1)
    b = b.removesuffix("까지")
    start = _clock(a, bare_ok=True)
    if start is None or not b:
        return None
    if d := _DUR.match(b):
        h, half, mins = d.groups()
        dur = int(h) * 60 + (30 if half else 0) if h else int(mins)
        total = start.hour * 60 + start.minute + dur
        if dur <= 0 or total >= 24 * 60:
            return None
        return TimeSpan(start, time(total // 60, total % 60))
    end = _clock(b, bare_ok=True)
    if end is None or end <= start:
        return None
    return TimeSpan(start, end)


def normalize_room(expr: str) -> str:
    """공백·'호' 정리. 범위·층·건물 표현은 그대로 둔다 — 방으로 푸는 일은 서버(DB)가 한다."""
    t = re.sub(r"\s+", " ", expr.strip())
    t = re.sub(r"(\d)\s*호", r"\1", t)
    t = re.sub(r"\s*([~\-])\s*", r"\1", t)
    t = re.sub(r"(\d)\s+층", r"\1층", t)
    return t.strip()
```

`assistant_proto/assistant_proto/__init__.py` 에 해석기를 더한다 (전체):
```python
"""관리자 AI 비서 양식 규격 v1 — 단일 진실원 (spec 2026-11-25 §3, 공통 부록 §1~§3).
서버(server/app/assistant)·학습(ml/)이 경로 의존성으로 쓴다. DB·네트워크 없음."""

from assistant_proto.form import (
    FIELD_ORDER,
    INTENTS,
    SCHEMA_VERSION,
    TYPE_LABELS,
    Fields,
    Form,
    FormError,
    canonical_json,
    form_to_dict,
    json_schema,
    parse_form,
    type_code,
)
from assistant_proto.resolve import (
    TimeSpan,
    When,
    normalize_room,
    resolve_time,
    resolve_weekdays,
    resolve_when,
)

__all__ = [
    "FIELD_ORDER",
    "INTENTS",
    "SCHEMA_VERSION",
    "TYPE_LABELS",
    "Fields",
    "Form",
    "FormError",
    "TimeSpan",
    "When",
    "canonical_json",
    "form_to_dict",
    "json_schema",
    "normalize_room",
    "parse_form",
    "resolve_time",
    "resolve_weekdays",
    "resolve_when",
    "type_code",
]
```

- [ ] **Step 4: 통과 + 커밋**

Run: `cd assistant_proto && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS. 예문이 하나라도 실패하면 **예문이 아니라 구현을** 고친다(예문 = 규칙의 원본). 규칙 자체를 바꿔야 하면 README 표(Task 3)도 같은 커밋에서.

```bash
git add assistant_proto/assistant_proto/resolve.py assistant_proto/assistant_proto/__init__.py \
  assistant_proto/vectors/resolve.v1.jsonl assistant_proto/tests/test_resolve.py
git commit -m "feat(proto): 해석기 — 날짜·기간·요일·시각·강의실 표현, 예문 84개"
```

---

### Task 3: 프롬프트 · 대화 규칙 · 계약 예문 · README

**Files:**
- Create: `assistant_proto/prompt/system.v1.txt`, `assistant_proto/assistant_proto/prompt.py`, `assistant_proto/assistant_proto/rules.py`, `assistant_proto/vectors/forms.v1.jsonl`, `assistant_proto/README.md`
- Modify: `assistant_proto/assistant_proto/__init__.py`
- Test: `assistant_proto/tests/test_prompt.py`, `assistant_proto/tests/test_rules.py`, `assistant_proto/tests/test_forms_vectors.py`

**Interfaces:**
- Consumes: Task 1 의 `FIELD_ORDER`·`INTENTS`·`ROOT`
- Produces:
  - `SYSTEM_PROMPT: str`, `FIRST_PREFIX = "관리자: "`, `render_prefix(intent, items, question) -> str` (부록 §2)
  - `rules.PRIMARY: dict[str, str]` — intent → 이어지는 답(`fill`)이 들어갈 칸 묶음(`"set"`·`"target"`)
  - `rules.missing(intent, target: dict, set_: dict) -> str | None` — 처음으로 빈 꼭 필요한 칸 `"set.subject"` 꼴, 다 찼으면 `None`. `"set.any"` = 수정에서 바꿀 값이 하나도 없음
  - `rules.question(intent, slot, type_label=None) -> str` — 그 칸을 묻는 문구
  - `rules.state_items(intent, target, set_, missing_slot=None) -> list[tuple[str, str | None]]` — `render_prefix` 의 `items`. **서버와 ml 이 같은 함수로 접두어를 만든다** (부록에 없는 공개 API 추가 — 보고서 참조)

- [ ] **Step 1: 시스템 지시문**

`assistant_proto/prompt/system.v1.txt` (전문, 끝 줄바꿈 하나):
```text
너는 강의실 관리 웹의 입력 변환기다. 관리자의 한국어 요청을 아래 양식의 JSON 한 줄로만 바꾼다. 설명·인사·코드블록 없이 JSON 만 출력한다.
양식: {"v":1,"intent":작업,"target":{찾을 조건},"set":{새 값}}
작업(intent):
- event.add / event.change / event.remove: 특정 날짜의 일정(특강·대여·휴강·보강·시험) 추가 / 수정 / 삭제
- exam.add / exam.change / exam.remove: 강의실 시험기간 추가 / 수정 / 삭제
- class.add / class.change / class.remove: 매주 반복되는 정규 시간표 추가 / 수정 / 삭제
- request.approve / request.reject: 학생 예약 신청 승인 / 거절
- ask.free_rooms(빈 강의실) / ask.schedule(강의실 일정) / ask.requests(대기 중인 신청) / ask.node(노드·문 앞 화면 상태): 조회
- fill: "질문:" 에 대한 답. 답에 나온 칸만 set 에 넣는다
- cancel: 취소·그만·처음부터
- unknown: 위 어디에도 없는 요청과 잡담
칸: rooms(강의실 목록) when(날짜·기간·요일) time(시각) type(수업|시험|휴강|빈강의실|특강|대여) subject(과목·행사 이름) professor(교수·담당자) reason(거절 사유) requester(신청자 이름·학번)
규칙:
1. 칸 값은 문장에 나온 표현을 글자 그대로 옮긴다. 날짜·시각을 계산하거나 바꾸지 않는다. 끝에 붙은 조사(을·를·은·는·이·가·로·으로·에·에서)는 뺀다.
2. type 만 고른다: 보강→수업, 세미나·초청강연→특강, 대관·사용→대여, 중간고사·기말고사→시험.
3. 추가는 set 에, 삭제·조회·승인·거절 대상은 target 에, 수정은 바꿀 대상을 target 에 · 새 값을 set 에 넣는다. 거절 사유는 set.reason.
4. 문장에 없는 칸은 넣지 않는다. 빈 값을 만들지 않는다.
5. "상태:" 와 "질문:" 줄은 앞선 대화다. 그 내용은 옮기지 않고 마지막 "관리자:" 뒤 문장만 바꾼다. 그 문장이 질문과 상관없는 새 요청이면 새 작업으로 바꾼다.
6. 키 순서: v, intent, target, set. 칸 순서: rooms, when, time, type, subject, professor, reason, requester.
```

- [ ] **Step 2: 실패하는 테스트**

`assistant_proto/tests/test_prompt.py`:
```python
from assistant_proto import FIELD_ORDER, FIRST_PREFIX, INTENTS, SYSTEM_PROMPT, TYPE_LABELS, render_prefix


def test_system_prompt_names_every_intent_field_and_type():
    for x in (*INTENTS, *FIELD_ORDER, *TYPE_LABELS):
        assert x in SYSTEM_PROMPT, x
    assert not SYSTEM_PROMPT.endswith("\n")


def test_render_prefix_matches_interface_example():
    p = render_prefix(
        "event.add",
        [("강의실", "803"), ("날짜", "11/27(금)"), ("시각", "15:00~18:00"), ("유형", "특강"), ("이름", None)],
        "특강 이름은 무엇인가요?",
    )
    assert p == (
        "상태: event.add | 강의실 803 | 날짜 11/27(금) | 시각 15:00~18:00 | 유형 특강 | 이름 ?\n"
        "질문: 특강 이름은 무엇인가요?\n"
        "관리자: "
    )
    assert FIRST_PREFIX == "관리자: " and p.endswith(FIRST_PREFIX)
```

`assistant_proto/tests/test_rules.py`:
```python
from assistant_proto import INTENTS, render_prefix, rules


def test_primary_covers_every_actionable_intent():
    assert set(rules.PRIMARY) == set(INTENTS) - {"fill", "cancel", "unknown"}
    assert rules.PRIMARY["event.add"] == "set" and rules.PRIMARY["event.change"] == "set"
    assert rules.PRIMARY["event.remove"] == "target" and rules.PRIMARY["ask.node"] == "target"


def test_missing_event_add_order():
    m = rules.missing
    assert m("event.add", {}, {}) == "set.rooms"
    assert m("event.add", {}, {"rooms": ["803"]}) == "set.when"
    assert m("event.add", {}, {"rooms": ["803"], "when": "금"}) == "set.type"
    base = {"rooms": ["803"], "when": "금", "type": "특강"}
    assert m("event.add", {}, base) == "set.time"
    assert m("event.add", {}, {**base, "time": "3~6시"}) == "set.subject"
    assert m("event.add", {}, {**base, "time": "3~6시", "subject": "알고리즘 특강"}) is None
    # 휴강은 시각·과목 없이도 된다 — 서버가 그날 정규 수업에서 찾는다
    assert m("event.add", {}, {"rooms": ["803"], "when": "금", "type": "휴강"}) is None


def test_missing_change_and_remove():
    m = rules.missing
    assert m("event.change", {}, {}) == "target.rooms"
    assert m("event.change", {"rooms": ["803"]}, {}) == "target.when"
    assert m("event.change", {"rooms": ["803"], "when": "금"}, {}) == "target.time"
    assert m("event.change", {"rooms": ["803"], "when": "금", "type": "특강"}, {}) == "set.any"
    assert m("event.change", {"rooms": ["803"], "when": "금", "type": "특강"}, {"time": "4시"}) is None
    assert m("event.remove", {"rooms": ["803"], "when": "금", "subject": "x"}, {}) is None
    assert m("class.remove", {"rooms": ["803"]}, {}) == "target.when"
    assert m("class.add", {}, {"rooms": ["803"], "when": "월", "time": "9~12시"}) == "set.subject"
    assert m("exam.add", {}, {"rooms": ["803"]}) == "set.when"
    assert m("exam.change", {"rooms": ["803"]}, {}) == "set.when"
    assert m("exam.remove", {}, {}) == "target.rooms"
    assert m("request.approve", {}, {}) is None
    assert m("ask.free_rooms", {}, {}) == "target.when"
    assert m("ask.schedule", {}, {}) == "target.rooms"
    assert m("ask.node", {}, {}) == "target.rooms"
    assert m("ask.requests", {}, {}) is None


def test_question_texts():
    q = rules.question
    assert q("event.add", "set.subject", "특강") == "특강 이름은 무엇인가요?"
    assert q("class.add", "set.subject") == "과목명은 무엇인가요?"
    assert q("class.add", "set.when") == "무슨 요일인가요? (예: 월, 화목)"
    assert q("exam.add", "set.when") == "시험기간은 언제부터 언제까지인가요? (예: 12/15~12/19)"
    assert q("event.add", "set.when") == "날짜는 언제인가요? (예: 12/3, 이번 주 금요일)"
    assert q("event.add", "set.time") == "몇 시부터 몇 시까지인가요? (예: 15시~18시)"
    assert q("event.change", "set.any").startswith("무엇을 어떻게 바꿀까요?")


def test_state_items_example_and_change_labels():
    items = rules.state_items(
        "event.add",
        {},
        {"rooms": ["803"], "when": "이번 주 금요일", "time": "15시부터 18시까지", "type": "특강"},
        "set.subject",
    )
    assert items == [
        ("강의실", "803"),
        ("날짜", "이번 주 금요일"),
        ("시각", "15시부터 18시까지"),
        ("유형", "특강"),
        ("이름", None),
    ]
    items = rules.state_items(
        "event.change", {"rooms": ["803", "801"], "when": "금요일", "type": "특강"}, {}, "set.any"
    )
    assert items == [("대상 강의실", "803, 801"), ("대상 날짜", "금요일"), ("대상 유형", "특강")]
    assert rules.state_items("class.add", {}, {"rooms": ["801"], "when": "월"}, "set.subject")[-1] == (
        "과목",
        None,
    )
    assert rules.state_items("exam.add", {}, {"rooms": ["801"]}, "set.when")[-1] == ("기간", None)
    # 칸이 아닌 빈 자리(선택지 고르기)는 상태에 넣지 않는다
    assert rules.state_items("event.remove", {"rooms": ["803"]}, {}, "target.pick") == [
        ("강의실", "803")
    ]


def test_render_with_state_items():
    p = render_prefix(
        "class.add",
        rules.state_items("class.add", {}, {"rooms": ["801"], "when": "월", "time": "9시~12시"}, "set.subject"),
        rules.question("class.add", "set.subject"),
    )
    assert p == "상태: class.add | 강의실 801 | 요일 월 | 시각 9시~12시 | 과목 ?\n질문: 과목명은 무엇인가요?\n관리자: "
```

`assistant_proto/tests/test_forms_vectors.py`:
```python
import json
from collections import Counter
from pathlib import Path

import jsonschema
import pytest

from assistant_proto import FIRST_PREFIX, INTENTS, canonical_json, json_schema, parse_form

VEC = Path(__file__).resolve().parents[1] / "vectors" / "forms.v1.jsonl"
ROWS = [json.loads(x) for x in VEC.read_text(encoding="utf-8").splitlines() if x.strip()]
SCHEMA = jsonschema.Draft202012Validator(json_schema())


def test_ids_unique_and_every_intent_has_four():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids))
    c = Counter(r["form"]["intent"] for r in ROWS)
    short = {i: c[i] for i in INTENTS if c[i] < 4}
    assert not short, short


@pytest.mark.parametrize("r", ROWS, ids=lambda r: r["id"])
def test_vector_valid_and_canonical(r):
    assert list(r) == ["id", "prefix", "utterance", "form"]
    assert not list(SCHEMA.iter_errors(r["form"]))
    f = parse_form(r["form"])
    # 파일의 키 순서도 정규형이다 — 학습 정답을 이 파일에서 그대로 뽑아도 같다
    assert canonical_json(f) == json.dumps(r["form"], ensure_ascii=False, separators=(",", ":"))
    assert r["prefix"].endswith(FIRST_PREFIX)


@pytest.mark.parametrize("r", ROWS, ids=lambda r: r["id"])
def test_values_copied_verbatim(r):
    """규칙 1 — type 말고는 문장(접두어 말고 관리자 문장)에 글자 그대로 있어야 한다."""
    for sec in ("target", "set"):
        for k, v in r["form"][sec].items():
            if k == "type":
                continue
            for x in v if k == "rooms" else [v]:
                assert x in r["utterance"], (r["id"], k, x)


def test_fill_always_has_context():
    for r in ROWS:
        if r["form"]["intent"] == "fill":
            assert r["prefix"] != FIRST_PREFIX and r["prefix"].startswith("상태: "), r["id"]
```

Run: `cd assistant_proto && uv run pytest -q`
Expected: FAIL — `ImportError: cannot import name 'FIRST_PREFIX'`.

- [ ] **Step 3: 구현 — prompt.py · rules.py · __init__**

`assistant_proto/assistant_proto/prompt.py`:
```python
"""모델 입력 (공통 부록 §2). 시스템 메시지 = SYSTEM_PROMPT, 사용자 메시지 = 접두어 + 관리자 문장.
첫 턴 접두어는 FIRST_PREFIX, 이어지는 턴은 서버가 render_prefix 로 만들어 준다."""

from __future__ import annotations

from assistant_proto.form import ROOT

FIRST_PREFIX = "관리자: "
SYSTEM_PROMPT: str = (ROOT / "prompt" / "system.v1.txt").read_text(encoding="utf-8").strip()


def render_prefix(intent: str, items: list[tuple[str, str | None]], question: str) -> str:
    parts = [intent, *(f"{label} {'?' if value is None else value}" for label, value in items)]
    return f"상태: {' | '.join(parts)}\n질문: {question}\n{FIRST_PREFIX}"
```

`assistant_proto/assistant_proto/rules.py`:
```python
"""대화 규칙 — 작업별 꼭 필요한 칸 · 묻는 문구 · 상태 요약 칸 (spec §3.3·§3.4).

서버(server/app/assistant)가 대화를 진행할 때 쓰고, ml 이 학습용 '이어지는 대화' 접두어를 서버와
글자 하나 다르지 않게 만들 때 쓴다. 순수 함수 — DB 없음."""

from __future__ import annotations

from assistant_proto.form import FIELD_ORDER

# 이어지는 답(fill)의 칸이 기본으로 들어갈 묶음. 수정은 '새 값'(set)이 기본이다
PRIMARY: dict[str, str] = {
    "event.add": "set",
    "exam.add": "set",
    "class.add": "set",
    "event.change": "set",
    "exam.change": "set",
    "class.change": "set",
    "event.remove": "target",
    "exam.remove": "target",
    "class.remove": "target",
    "request.approve": "target",
    "request.reject": "target",
    "ask.free_rooms": "target",
    "ask.schedule": "target",
    "ask.requests": "target",
    "ask.node": "target",
}
CHANGE_INTENTS = ("event.change", "exam.change", "class.change")
_LABEL = {
    "rooms": "강의실",
    "time": "시각",
    "type": "유형",
    "professor": "교수",
    "reason": "사유",
    "requester": "신청자",
}


def _first(sec: str, d: dict, fields: tuple[str, ...]) -> str | None:
    for f in fields:
        if f not in d:
            return f"{sec}.{f}"
    return None


def missing(intent: str, target: dict, set_: dict) -> str | None:
    t, st = target, set_
    if intent == "event.add":
        if slot := _first("set", st, ("rooms", "when", "type")):
            return slot
        if st["type"] == "휴강":  # 시각·과목은 그날 정규 수업에서 찾는다(서버)
            return None
        return _first("set", st, ("time", "subject"))
    if intent in ("event.change", "event.remove", "class.change", "class.remove"):
        if slot := _first("target", t, ("rooms", "when")):
            return slot
        if not {"time", "subject", "type"} & t.keys():
            return "target.time"
        if intent in CHANGE_INTENTS and not st:
            return "set.any"
        return None
    if intent == "exam.add":
        return _first("set", st, ("rooms", "when"))
    if intent == "exam.change":
        return _first("target", t, ("rooms",)) or _first("set", st, ("when",))
    if intent == "exam.remove":
        return _first("target", t, ("rooms",))
    if intent == "class.add":
        return _first("set", st, ("rooms", "when", "time", "subject"))
    if intent == "ask.free_rooms":
        return _first("target", t, ("when",))
    if intent in ("ask.schedule", "ask.node"):
        return _first("target", t, ("rooms",))
    return None  # request.*, ask.requests — 조건이 없어도 목록에서 고른다


def question(intent: str, slot: str, type_label: str | None = None) -> str:
    grp = intent.split(".")[0]
    sec, f = slot.split(".")
    if f == "rooms":
        return "어느 강의실인가요? (예: 803, 공학관 803, 8층 전체)"
    if f == "when":
        if grp == "class":
            return "무슨 요일인가요? (예: 월, 화목)"
        if grp == "exam":
            return "시험기간은 언제부터 언제까지인가요? (예: 12/15~12/19)"
        if sec == "target":
            return "언제 일정인가요? (예: 이번 주 금요일, 12/3)"
        return "날짜는 언제인가요? (예: 12/3, 이번 주 금요일)"
    if f == "time":
        if sec == "target":
            return "몇 시 일정인가요? 과목·행사 이름으로 알려 주셔도 됩니다."
        return "몇 시부터 몇 시까지인가요? (예: 15시~18시)"
    if f == "type":
        return "어떤 일정인가요? 특강·대여·휴강·보강·시험 중에서 골라 주세요."
    if f == "subject":
        return "과목명은 무엇인가요?" if grp == "class" else f"{type_label or '일정'} 이름은 무엇인가요?"
    if f == "any":
        return "무엇을 어떻게 바꿀까요? (예: 16시부터 18시까지로, 이름을 ○○로)"
    return "조금 더 자세히 알려 주세요."


def _label(intent: str, sec: str, f: str) -> str:
    grp = intent.split(".")[0]
    if f == "when":
        base = {"class": "요일", "exam": "기간"}.get(grp, "날짜")
    elif f == "subject":
        base = "과목" if grp == "class" else "이름"
    else:
        base = _LABEL[f]
    return f"대상 {base}" if sec == "target" and intent in CHANGE_INTENTS else base


def state_items(
    intent: str, target: dict, set_: dict, missing_slot: str | None = None
) -> list[tuple[str, str | None]]:
    """render_prefix 의 items — 채운 칸은 표현 그대로(rooms 는 ', ' 로 잇는다), 묻는 칸은 None('?')."""
    items: list[tuple[str, str | None]] = []
    for sec, d in (("target", target), ("set", set_)):
        for f in FIELD_ORDER:
            if f in d:
                v = d[f]
                items.append((_label(intent, sec, f), ", ".join(v) if f == "rooms" else v))
    if missing_slot:
        sec, f = missing_slot.split(".")
        d = target if sec == "target" else set_
        if f in FIELD_ORDER and f not in d:
            items.append((_label(intent, sec, f), None))
    return items
```

`assistant_proto/assistant_proto/__init__.py` (전체):
```python
"""관리자 AI 비서 양식 규격 v1 — 단일 진실원 (spec 2026-11-25 §3, 공통 부록 §1~§3).
서버(server/app/assistant)·학습(ml/)이 경로 의존성으로 쓴다. DB·네트워크 없음."""

from assistant_proto import rules
from assistant_proto.form import (
    FIELD_ORDER,
    INTENTS,
    SCHEMA_VERSION,
    TYPE_LABELS,
    Fields,
    Form,
    FormError,
    canonical_json,
    form_to_dict,
    json_schema,
    parse_form,
    type_code,
)
from assistant_proto.prompt import FIRST_PREFIX, SYSTEM_PROMPT, render_prefix
from assistant_proto.resolve import (
    TimeSpan,
    When,
    normalize_room,
    resolve_time,
    resolve_weekdays,
    resolve_when,
)

__all__ = [
    "FIELD_ORDER",
    "FIRST_PREFIX",
    "INTENTS",
    "SCHEMA_VERSION",
    "SYSTEM_PROMPT",
    "TYPE_LABELS",
    "Fields",
    "Form",
    "FormError",
    "TimeSpan",
    "When",
    "canonical_json",
    "form_to_dict",
    "json_schema",
    "normalize_room",
    "parse_form",
    "render_prefix",
    "resolve_time",
    "resolve_weekdays",
    "resolve_when",
    "rules",
    "type_code",
]
```

- [ ] **Step 4: 계약 예문 (intent 마다 4개 이상, 학습에 넣지 않음)**

`assistant_proto/vectors/forms.v1.jsonl` — 한 줄에 `id`·`prefix`·`utterance`·`form`, `form` 은 정규 키 순서:
```jsonl
{"id":"event.add-1","prefix":"관리자: ","utterance":"803호 이번주 금요일 15시부터 18시까지 특강 예약해줘","form":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803호"],"when":"이번주 금요일","time":"15시부터 18시까지","type":"특강"}}}
{"id":"event.add-2","prefix":"관리자: ","utterance":"다음 주 화요일 공학관 801 자료구조 휴강","form":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["공학관 801"],"when":"다음 주 화요일","type":"휴강","subject":"자료구조"}}}
{"id":"event.add-3","prefix":"관리자: ","utterance":"803 목요일 3시~6시 알고리즘 보강 잡아줘 김교수","form":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"],"when":"목요일","time":"3시~6시","type":"수업","subject":"알고리즘","professor":"김교수"}}}
{"id":"event.add-4","prefix":"관리자: ","utterance":"12/3 801, 803 오후 2시부터 4시 학생회 행사로 대관","form":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["801","803"],"when":"12/3","time":"오후 2시부터 4시","type":"대여","subject":"학생회 행사"}}}
{"id":"event.add-5","prefix":"관리자: ","utterance":"8층 전체 12/24 휴강","form":{"v":1,"intent":"event.add","target":{},"set":{"rooms":["8층 전체"],"when":"12/24","type":"휴강"}}}
{"id":"event.change-1","prefix":"관리자: ","utterance":"803 금요일 특강 16시로 바꿔줘","form":{"v":1,"intent":"event.change","target":{"rooms":["803"],"when":"금요일","type":"특강"},"set":{"time":"16시"}}}
{"id":"event.change-2","prefix":"관리자: ","utterance":"801 다음 주 화요일 휴강을 수요일로 옮겨줘","form":{"v":1,"intent":"event.change","target":{"rooms":["801"],"when":"다음 주 화요일","type":"휴강"},"set":{"when":"수요일"}}}
{"id":"event.change-3","prefix":"관리자: ","utterance":"12/3 803 대관 이름을 동아리 발표회로 바꿔","form":{"v":1,"intent":"event.change","target":{"rooms":["803"],"when":"12/3","type":"대여"},"set":{"subject":"동아리 발표회"}}}
{"id":"event.change-4","prefix":"관리자: ","utterance":"이번주 목요일 803 보강 시간 3시부터 5시로 변경","form":{"v":1,"intent":"event.change","target":{"rooms":["803"],"when":"이번주 목요일","type":"수업"},"set":{"time":"3시부터 5시"}}}
{"id":"event.remove-1","prefix":"관리자: ","utterance":"803 이번주 금요일 특강 삭제해줘","form":{"v":1,"intent":"event.remove","target":{"rooms":["803"],"when":"이번주 금요일","type":"특강"},"set":{}}}
{"id":"event.remove-2","prefix":"관리자: ","utterance":"12/24 8층 전체 휴강 지워","form":{"v":1,"intent":"event.remove","target":{"rooms":["8층 전체"],"when":"12/24","type":"휴강"},"set":{}}}
{"id":"event.remove-3","prefix":"관리자: ","utterance":"801 내일 오후 2시 대관 없애줘","form":{"v":1,"intent":"event.remove","target":{"rooms":["801"],"when":"내일","time":"오후 2시","type":"대여"},"set":{}}}
{"id":"event.remove-4","prefix":"관리자: ","utterance":"다음 주 월요일 803 알고리즘 보강 취소","form":{"v":1,"intent":"event.remove","target":{"rooms":["803"],"when":"다음 주 월요일","type":"수업","subject":"알고리즘"},"set":{}}}
{"id":"exam.add-1","prefix":"관리자: ","utterance":"801, 803 12/15~19 시험기간으로 설정","form":{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["801","803"],"when":"12/15~19"}}}
{"id":"exam.add-2","prefix":"관리자: ","utterance":"공학관 8층 전체 다음 주 월요일부터 금요일까지 시험기간","form":{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["공학관 8층 전체"],"when":"다음 주 월요일부터 금요일까지"}}}
{"id":"exam.add-3","prefix":"관리자: ","utterance":"803 기말고사 기간 12월 14일부터 18일까지","form":{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["803"],"when":"12월 14일부터 18일까지"}}}
{"id":"exam.add-4","prefix":"관리자: ","utterance":"802호 12/8~12/12 중간고사 기간 등록","form":{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["802호"],"when":"12/8~12/12"}}}
{"id":"exam.change-1","prefix":"관리자: ","utterance":"803 시험기간을 12/16~20 으로 바꿔","form":{"v":1,"intent":"exam.change","target":{"rooms":["803"]},"set":{"when":"12/16~20"}}}
{"id":"exam.change-2","prefix":"관리자: ","utterance":"801 12/15~19 시험기간을 12/14~18 로 변경","form":{"v":1,"intent":"exam.change","target":{"rooms":["801"],"when":"12/15~19"},"set":{"when":"12/14~18"}}}
{"id":"exam.change-3","prefix":"관리자: ","utterance":"공학관 803 시험기간 다음 주 월요일부터 금요일까지로 변경","form":{"v":1,"intent":"exam.change","target":{"rooms":["공학관 803"]},"set":{"when":"다음 주 월요일부터 금요일까지"}}}
{"id":"exam.change-4","prefix":"관리자: ","utterance":"802 중간고사 기간 12/9~12/13으로 수정","form":{"v":1,"intent":"exam.change","target":{"rooms":["802"]},"set":{"when":"12/9~12/13"}}}
{"id":"exam.remove-1","prefix":"관리자: ","utterance":"803 시험기간 삭제","form":{"v":1,"intent":"exam.remove","target":{"rooms":["803"]},"set":{}}}
{"id":"exam.remove-2","prefix":"관리자: ","utterance":"801 12/15~19 시험기간 지워줘","form":{"v":1,"intent":"exam.remove","target":{"rooms":["801"],"when":"12/15~19"},"set":{}}}
{"id":"exam.remove-3","prefix":"관리자: ","utterance":"8층 전체 시험기간 해제","form":{"v":1,"intent":"exam.remove","target":{"rooms":["8층 전체"]},"set":{}}}
{"id":"exam.remove-4","prefix":"관리자: ","utterance":"공학관 802 기말고사 기간 취소해","form":{"v":1,"intent":"exam.remove","target":{"rooms":["공학관 802"]},"set":{}}}
{"id":"class.add-1","prefix":"관리자: ","utterance":"803 월 9시~12시 자료구조 김교수 수업 추가","form":{"v":1,"intent":"class.add","target":{},"set":{"rooms":["803"],"when":"월","time":"9시~12시","type":"수업","subject":"자료구조","professor":"김교수"}}}
{"id":"class.add-2","prefix":"관리자: ","utterance":"801 매주 화목 오후 3시부터 4시 15분 알고리즘 정규 수업 넣어줘","form":{"v":1,"intent":"class.add","target":{},"set":{"rooms":["801"],"when":"매주 화목","time":"오후 3시부터 4시 15분","type":"수업","subject":"알고리즘"}}}
{"id":"class.add-3","prefix":"관리자: ","utterance":"공학관 802 수요일 10시부터 12시 캡스톤디자인 박교수","form":{"v":1,"intent":"class.add","target":{},"set":{"rooms":["공학관 802"],"when":"수요일","time":"10시부터 12시","subject":"캡스톤디자인","professor":"박교수"}}}
{"id":"class.add-4","prefix":"관리자: ","utterance":"803 금요일마다 1시~3시 세미나 정규 편성","form":{"v":1,"intent":"class.add","target":{},"set":{"rooms":["803"],"when":"금요일마다","time":"1시~3시","type":"특강","subject":"세미나"}}}
{"id":"class.change-1","prefix":"관리자: ","utterance":"803 월요일 자료구조 교수 이교수로 바꿔","form":{"v":1,"intent":"class.change","target":{"rooms":["803"],"when":"월요일","subject":"자료구조"},"set":{"professor":"이교수"}}}
{"id":"class.change-2","prefix":"관리자: ","utterance":"801 화요일 3시 수업 4시로 옮겨줘","form":{"v":1,"intent":"class.change","target":{"rooms":["801"],"when":"화요일","time":"3시","type":"수업"},"set":{"time":"4시"}}}
{"id":"class.change-3","prefix":"관리자: ","utterance":"802 수요일 캡스톤디자인 10시부터 1시까지로 변경","form":{"v":1,"intent":"class.change","target":{"rooms":["802"],"when":"수요일","subject":"캡스톤디자인"},"set":{"time":"10시부터 1시까지"}}}
{"id":"class.change-4","prefix":"관리자: ","utterance":"공학관 803 목 9시 수업 과목명 운영체제로 수정","form":{"v":1,"intent":"class.change","target":{"rooms":["공학관 803"],"when":"목","time":"9시","type":"수업"},"set":{"subject":"운영체제"}}}
{"id":"class.remove-1","prefix":"관리자: ","utterance":"803 월요일 자료구조 수업 삭제","form":{"v":1,"intent":"class.remove","target":{"rooms":["803"],"when":"월요일","type":"수업","subject":"자료구조"},"set":{}}}
{"id":"class.remove-2","prefix":"관리자: ","utterance":"801 화요일 오후 3시 수업 빼줘","form":{"v":1,"intent":"class.remove","target":{"rooms":["801"],"when":"화요일","time":"오후 3시","type":"수업"},"set":{}}}
{"id":"class.remove-3","prefix":"관리자: ","utterance":"공학관 802 매주 수요일 캡스톤디자인 없애","form":{"v":1,"intent":"class.remove","target":{"rooms":["공학관 802"],"when":"매주 수요일","subject":"캡스톤디자인"},"set":{}}}
{"id":"class.remove-4","prefix":"관리자: ","utterance":"803 금요일 세미나 정규 시간표에서 지워","form":{"v":1,"intent":"class.remove","target":{"rooms":["803"],"when":"금요일","subject":"세미나"},"set":{}}}
{"id":"request.approve-1","prefix":"관리자: ","utterance":"801 내일 신청 승인해줘","form":{"v":1,"intent":"request.approve","target":{"rooms":["801"],"when":"내일"},"set":{}}}
{"id":"request.approve-2","prefix":"관리자: ","utterance":"김민수 학생 예약 승인","form":{"v":1,"intent":"request.approve","target":{"requester":"김민수"},"set":{}}}
{"id":"request.approve-3","prefix":"관리자: ","utterance":"803 금요일 오후 2시 대여 신청 승인","form":{"v":1,"intent":"request.approve","target":{"rooms":["803"],"when":"금요일","time":"오후 2시","type":"대여"},"set":{}}}
{"id":"request.approve-4","prefix":"관리자: ","utterance":"20231234 신청 허락해줘","form":{"v":1,"intent":"request.approve","target":{"requester":"20231234"},"set":{}}}
{"id":"request.approve-5","prefix":"상태: event.add | 강의실 803 | 날짜 이번 주 금요일 | 시각 15시부터 18시까지 | 유형 특강 | 이름 ?\n질문: 특강 이름은 무엇인가요?\n관리자: ","utterance":"아 그거 말고 801 내일 신청 승인해줘","form":{"v":1,"intent":"request.approve","target":{"rooms":["801"],"when":"내일"},"set":{}}}
{"id":"request.reject-1","prefix":"관리자: ","utterance":"801 내일 신청 거절해 장비 점검 때문에","form":{"v":1,"intent":"request.reject","target":{"rooms":["801"],"when":"내일"},"set":{"reason":"장비 점검 때문에"}}}
{"id":"request.reject-2","prefix":"관리자: ","utterance":"김민수 예약 신청 반려, 사유는 시험 기간","form":{"v":1,"intent":"request.reject","target":{"requester":"김민수"},"set":{"reason":"시험 기간"}}}
{"id":"request.reject-3","prefix":"관리자: ","utterance":"803 12/3 신청 거절","form":{"v":1,"intent":"request.reject","target":{"rooms":["803"],"when":"12/3"},"set":{}}}
{"id":"request.reject-4","prefix":"관리자: ","utterance":"이영희 학생 신청은 강의실 공사로 거절","form":{"v":1,"intent":"request.reject","target":{"requester":"이영희"},"set":{"reason":"강의실 공사"}}}
{"id":"ask.free_rooms-1","prefix":"관리자: ","utterance":"이번주 금요일 오후 2시부터 5시까지 빈 강의실 있어?","form":{"v":1,"intent":"ask.free_rooms","target":{"when":"이번주 금요일","time":"오후 2시부터 5시까지"},"set":{}}}
{"id":"ask.free_rooms-2","prefix":"관리자: ","utterance":"내일 빈 강의실 알려줘","form":{"v":1,"intent":"ask.free_rooms","target":{"when":"내일"},"set":{}}}
{"id":"ask.free_rooms-3","prefix":"관리자: ","utterance":"8층에서 12/3 10시~12시 비어있는 강의실","form":{"v":1,"intent":"ask.free_rooms","target":{"rooms":["8층"],"when":"12/3","time":"10시~12시"},"set":{}}}
{"id":"ask.free_rooms-4","prefix":"관리자: ","utterance":"공학관 다음 주 월요일 빈 방","form":{"v":1,"intent":"ask.free_rooms","target":{"rooms":["공학관"],"when":"다음 주 월요일"},"set":{}}}
{"id":"ask.schedule-1","prefix":"관리자: ","utterance":"803 이번주 일정 보여줘","form":{"v":1,"intent":"ask.schedule","target":{"rooms":["803"],"when":"이번주"},"set":{}}}
{"id":"ask.schedule-2","prefix":"관리자: ","utterance":"801 내일 뭐 있어?","form":{"v":1,"intent":"ask.schedule","target":{"rooms":["801"],"when":"내일"},"set":{}}}
{"id":"ask.schedule-3","prefix":"관리자: ","utterance":"공학관 802 시간표 알려줘","form":{"v":1,"intent":"ask.schedule","target":{"rooms":["공학관 802"]},"set":{}}}
{"id":"ask.schedule-4","prefix":"관리자: ","utterance":"803 12/3 일정","form":{"v":1,"intent":"ask.schedule","target":{"rooms":["803"],"when":"12/3"},"set":{}}}
{"id":"ask.requests-1","prefix":"관리자: ","utterance":"대기 중인 신청 보여줘","form":{"v":1,"intent":"ask.requests","target":{},"set":{}}}
{"id":"ask.requests-2","prefix":"관리자: ","utterance":"801 예약 신청 들어온 거 있어?","form":{"v":1,"intent":"ask.requests","target":{"rooms":["801"]},"set":{}}}
{"id":"ask.requests-3","prefix":"관리자: ","utterance":"내일 신청 목록","form":{"v":1,"intent":"ask.requests","target":{"when":"내일"},"set":{}}}
{"id":"ask.requests-4","prefix":"관리자: ","utterance":"승인 기다리는 예약 몇 개야","form":{"v":1,"intent":"ask.requests","target":{},"set":{}}}
{"id":"ask.node-1","prefix":"관리자: ","utterance":"801 노드 배터리 얼마야?","form":{"v":1,"intent":"ask.node","target":{"rooms":["801"]},"set":{}}}
{"id":"ask.node-2","prefix":"관리자: ","utterance":"803 문 앞 화면 잘 붙어있어?","form":{"v":1,"intent":"ask.node","target":{"rooms":["803"]},"set":{}}}
{"id":"ask.node-3","prefix":"관리자: ","utterance":"8층 전체 노드 상태","form":{"v":1,"intent":"ask.node","target":{"rooms":["8층 전체"]},"set":{}}}
{"id":"ask.node-4","prefix":"관리자: ","utterance":"공학관 802 단말 신호 어때","form":{"v":1,"intent":"ask.node","target":{"rooms":["공학관 802"]},"set":{}}}
{"id":"fill-1","prefix":"상태: event.add | 강의실 803 | 날짜 이번 주 금요일 | 시각 15시부터 18시까지 | 유형 특강 | 이름 ?\n질문: 특강 이름은 무엇인가요?\n관리자: ","utterance":"알고리즘 특강이요","form":{"v":1,"intent":"fill","target":{},"set":{"subject":"알고리즘 특강"}}}
{"id":"fill-2","prefix":"상태: event.add | 강의실 803 | 유형 대여 | 이름 동아리 회의 | 날짜 ?\n질문: 날짜는 언제인가요? (예: 12/3, 이번 주 금요일)\n관리자: ","utterance":"다음 주 수요일 오후 4시부터 6시","form":{"v":1,"intent":"fill","target":{},"set":{"when":"다음 주 수요일","time":"오후 4시부터 6시"}}}
{"id":"fill-3","prefix":"상태: event.add | 강의실 803 | 날짜 내일 | 시각 3시~5시 | 유형 대여 | 이름 스터디\n질문: 확인 화면을 보고 [적용]을 눌러 주세요. 바꿀 것이 있으면 말씀해 주세요.\n관리자: ","utterance":"아 801도 같이","form":{"v":1,"intent":"fill","target":{},"set":{"rooms":["801"]}}}
{"id":"fill-4","prefix":"상태: class.add | 강의실 801 | 요일 월 | 시각 9시~12시 | 과목 ?\n질문: 과목명은 무엇인가요?\n관리자: ","utterance":"자료구조, 김교수님","form":{"v":1,"intent":"fill","target":{},"set":{"subject":"자료구조","professor":"김교수님"}}}
{"id":"fill-5","prefix":"상태: event.change | 대상 강의실 803 | 대상 날짜 금요일 | 대상 유형 특강\n질문: 무엇을 어떻게 바꿀까요? (예: 16시부터 18시까지로, 이름을 ○○로)\n관리자: ","utterance":"17시부터 19시까지로","form":{"v":1,"intent":"fill","target":{},"set":{"time":"17시부터 19시까지"}}}
{"id":"cancel-1","prefix":"관리자: ","utterance":"취소","form":{"v":1,"intent":"cancel","target":{},"set":{}}}
{"id":"cancel-2","prefix":"관리자: ","utterance":"아니 그만할게","form":{"v":1,"intent":"cancel","target":{},"set":{}}}
{"id":"cancel-3","prefix":"상태: event.add | 강의실 803 | 날짜 이번 주 금요일 | 시각 15시부터 18시까지 | 유형 특강 | 이름 ?\n질문: 특강 이름은 무엇인가요?\n관리자: ","utterance":"됐어 안 할래","form":{"v":1,"intent":"cancel","target":{},"set":{}}}
{"id":"cancel-4","prefix":"관리자: ","utterance":"처음부터 다시","form":{"v":1,"intent":"cancel","target":{},"set":{}}}
{"id":"unknown-1","prefix":"관리자: ","utterance":"지난달 가장 많이 빈 강의실이 어디야?","form":{"v":1,"intent":"unknown","target":{},"set":{}}}
{"id":"unknown-2","prefix":"관리자: ","utterance":"안녕","form":{"v":1,"intent":"unknown","target":{},"set":{}}}
{"id":"unknown-3","prefix":"관리자: ","utterance":"803호 강의실 삭제해줘","form":{"v":1,"intent":"unknown","target":{},"set":{}}}
{"id":"unknown-4","prefix":"관리자: ","utterance":"점심 뭐 먹지","form":{"v":1,"intent":"unknown","target":{},"set":{}}}
{"id":"unknown-5","prefix":"관리자: ","utterance":"801 노드 재부팅해줘","form":{"v":1,"intent":"unknown","target":{},"set":{}}}
```

- [ ] **Step 5: README (해석 규칙 표 · lockstep 절차)**

`assistant_proto/README.md`:
````markdown
# assistant_proto — 관리자 AI 비서 양식 규격 v1 (단일 진실원)

- 설계: `docs/specs/2026-11-25-admin-ai-assistant-design.md` §3 · 공통 부록 `docs/plans/2026-11-25-ai-assistant-00-interfaces.md`
- 소유: PM(@ssenu). 모델(`ml/`, wj)이 내는 양식, 서버(`server/app/assistant/`, cw)가 읽는 양식, 웹이 출력 문법으로 쓰는 JSON Schema 가 모두 여기서 나온다. DB·네트워크 없음.

## 파일

| 경로 | 내용 |
|---|---|
| `schema/form.v1.json` | 양식 JSON Schema — 모델 출력 문법 강제에 그대로 쓴다 |
| `prompt/system.v1.txt` | 시스템 지시문 |
| `vectors/forms.v1.jsonl` | 계약 예문 (접두어 + 문장 → 정답 양식). **학습에 넣지 않는다** — 서버 테스트·모델 평가용 |
| `vectors/resolve.v1.jsonl` | 해석기 예문 (기준 시각 2026-11-25(수) 10:00 KST) |
| `assistant_proto/form.py` | `parse_form` · `form_to_dict` · `canonical_json` · `json_schema` · `type_code` |
| `assistant_proto/resolve.py` | `resolve_when` · `resolve_weekdays` · `resolve_time` · `normalize_room` |
| `assistant_proto/prompt.py` | `SYSTEM_PROMPT` · `FIRST_PREFIX` · `render_prefix` |
| `assistant_proto/rules.py` | `PRIMARY` · `missing` · `question` · `state_items` — 서버와 ml 이 같은 접두어를 만든다 |

## 해석 규칙 (원본은 `vectors/resolve.v1.jsonl`)

| 표현 | 값 | 예 (기준 11/25 수) |
|---|---|---|
| 오늘 · 내일 · 모레 · 내일모레 · 글피 | 오늘 +0·1·2·2·3 | 내일 → 11/26 |
| 이번 주·금주 / 다음 주·담주 / 다다음 주 / 지난주·저번주 + 요일 | 그 주(월요일 시작)의 그 요일 | 다음 주 화요일 → 12/1 |
| 이번 주 · 다음 주 (요일 없음) | 그 주 월~일 기간 | 이번 주 → 11/23~11/29 |
| 요일만 (금, 금요일) | 오늘 포함 가장 가까운 그 요일 | 수요일 → 11/25, 화 → 12/1 |
| 요일 여러 개 (화목, 화, 목) | 각각 가장 가까운 날 | 화목 → 11/26, 12/1 |
| 12/3 · 12월 3일 · 12.3 · 2026-12-07 | 올해, 지났으면 내년 | 11/20 → 2027-11-20 |
| 3일 | 이번 달, 지났으면 다음 달 | 3일 → 12/3 |
| 기간 A~B · A-B · A부터 B까지 | B 가 일만이면 A 의 달(앞이면 다음 달), 월/일이면 A 뒤 가장 가까운 날 | 12/28~1/3 → 2027-01-03 까지 |
| 이번 주 월~금 | 그 주 월~금 | 11/23~11/27 |
| 매주 월 · 월요일마다 · 매주 월수금 | 요일 반복(weekdays) | [1, 3, 5] |
| 시각 15시 · 15:30 · 3시 반 · 오후 2시 30분 · 정오 | 오전·오후 없는 1~8시는 13~20시 | 3시 → 15:00, 9시 → 09:00 |
| 구간 A부터 B · A~B · A-B, 길이 A부터 3시간 | 끝 ≤ 시작이면 못 풂 | 3시부터 3시간 → 15:00~18:00 |
| 끝만 (6시까지) · 모르는 표현 | 못 풂(None) — 서버가 되묻는다 | |
| 강의실 803호 · 801호~805호 · 8 층 전체 | 공백·'호' 정리만 (방으로 푸는 일은 서버) | 801~805 |

## 바꾸는 절차 (lockstep — 루트 CLAUDE.md 계층 규율)

1. 이 폴더만 바꾸는 PR 을 **단독으로 먼저** 머지한다(PM). 예문·README·코드를 한 커밋에서 함께.
2. 그 규칙을 쓰는 서버 PR (`server/app/assistant/`).
3. 양식 판(`v`)을 올렸으면 `ml/` 재학습 → 새 모델 릴리스(`server/app/assistant/model.json`). 서버는 다른 판 양식에 409 를 준다.
4. 웹은 규격 코드를 갖지 않는다(`GET /api/assistant/model` 로 받음) — 고칠 것 없음.

```bash
cd assistant_proto && uv sync && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```
````

- [ ] **Step 6: 통과 + 커밋**

Run: `cd assistant_proto && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (계약 예문 76개 × 2 테스트 + 해석기 예문 84개 + 나머지).

```bash
git add assistant_proto/prompt/system.v1.txt assistant_proto/assistant_proto/prompt.py \
  assistant_proto/assistant_proto/rules.py assistant_proto/assistant_proto/__init__.py \
  assistant_proto/vectors/forms.v1.jsonl assistant_proto/README.md \
  assistant_proto/tests/test_prompt.py assistant_proto/tests/test_rules.py assistant_proto/tests/test_forms_vectors.py
git commit -m "feat(proto): 시스템 지시문·대화 규칙·계약 예문 76개·README(해석 규칙표·lockstep)"
```

---

### Task 4: CI job · pre-commit · PR A

**Files:**
- Modify: `.github/workflows/ci.yml` (changes 필터·출력 + 새 job), `.pre-commit-config.yaml` (ruff 경로)

**Interfaces:** 없음

- [ ] **Step 1: CI — `changes` job 출력·필터**

`.github/workflows/ci.yml` 의 `changes.outputs` 에 한 줄 추가 (`proto:` 줄 아래):
```yaml
      assistant_proto: ${{ steps.filter.outputs.assistant_proto }}
```
`filters: |` 안, `proto:` 블록 아래에 추가:
```yaml
            assistant_proto:
              - 'assistant_proto/**'
              - '.github/workflows/ci.yml'
```

- [ ] **Step 2: CI — 새 job (proto job 바로 아래)**

```yaml
  # ===== assistant_proto: 관리자 AI 비서 양식 규격 (검증·해석기·예문) =====
  assistant_proto:
    needs: changes
    if: ${{ needs.changes.outputs.assistant_proto == 'true' }}
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: assistant_proto
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
      - name: test (양식·해석기·대화 규칙·예문)
        run: uv run pytest -q
```

- [ ] **Step 3: pre-commit ruff 경로**

`.pre-commit-config.yaml` 의 ruff 두 훅 `files:` 를 둘 다 바꾼다:
```yaml
        files: '^(server|modempi|lora_proto|assistant_proto|firmware/tools)/'
```

- [ ] **Step 4: 게이트 + 커밋**

Run:
```bash
cd assistant_proto && uv sync --frozen && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd .. && python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"
```
Expected: 전부 PASS, YAML 파싱 오류 없음.

```bash
git add .github/workflows/ci.yml .pre-commit-config.yaml
git commit -m "chore(infra): CI assistant_proto job · pre-commit ruff 경로"
```

- [ ] **Step 5: PR A**

```bash
git push -u origin feature/assistant-proto
gh pr create --base main --title "feat(proto): assistant_proto v1 — 관리자 AI 비서 양식 규격" --body-file - <<'EOF'
## 요약
관리자 AI 비서(spec `docs/specs/2026-11-25-admin-ai-assistant-design.md` §3)의 양식 규격 패키지. `lora_proto/` 와 같은 단일 진실원.

- 양식 v1 JSON Schema + 의존성 없는 검증·정규 직렬화 (`parse_form`·`canonical_json`)
- 해석기: 날짜·기간·요일·시각·강의실 표현 → 값 (예문 84개)
- 대화 규칙: 작업별 꼭 필요한 칸·질문 문구·상태 요약 칸 (서버·ml 공용)
- 시스템 지시문 + 계약 예문 76개 (학습에 넣지 않음)
- CI `assistant_proto` job

## ⚠️ lockstep
**이 PR 을 단독으로 먼저 머지한다.** 서버 PR(B, `feature/assistant-server`)과 `ml/`·웹 작업은 이 머지 뒤에 이 규격을 따른다.

## 게이트
- `cd assistant_proto && uv run pytest -q` — (통과 수 기입)
- `uv run ruff check . && uv run ruff format --check .`
EOF
```

**PR A 머지(팀장) 뒤에 PR B 를 시작한다.**

---

## PR B — 서버 백엔드 (PR A 머지 후)

```bash
git switch main && git pull --ff-only && git switch -c feature/assistant-server
```

모든 서버 명령은 `cd server` 에서. 공통 게이트: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`

### Task 5: 서버가 `assistant_proto` 를 쓰게 — 의존성 · Docker · CI

**Files:**
- Modify: `server/pyproject.toml`, `server/uv.lock`, `server/Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`
- Test: `server/tests/test_assistant_proto_dep.py`

**Interfaces:**
- Consumes: PR A 의 `assistant_proto` 공개 API
- Produces: 서버 venv·Docker 이미지에서 `import assistant_proto` 가 되고 schema·prompt 파일을 읽을 수 있다

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_proto_dep.py`:
```python
def test_assistant_proto_importable_with_data_files():
    import assistant_proto as A

    assert A.SCHEMA_VERSION == 1 and "event.add" in A.SYSTEM_PROMPT
    assert A.json_schema()["properties"]["v"] == {"const": 1}
    assert A.rules.missing("event.add", {}, {}) == "set.rooms"
```

Run: `uv run pytest tests/test_assistant_proto_dep.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'assistant_proto'`.

- [ ] **Step 2: 경로 의존성**

`server/pyproject.toml` — `dependencies` 의 `"lora-proto",` 아래에 `"assistant-proto",` 를 넣고, `[tool.uv.sources]` 를:
```toml
[tool.uv.sources]
lora-proto = { path = "../lora_proto", editable = true }
assistant-proto = { path = "../assistant_proto", editable = true }
```

Run: `uv lock && uv sync && uv run pytest tests/test_assistant_proto_dep.py -q`
Expected: PASS.

- [ ] **Step 3: Docker 이미지에 `assistant_proto/`**

`server/Dockerfile` — `COPY lora_proto/ lora_proto/` 바로 아래 한 줄:
```dockerfile
COPY assistant_proto/ assistant_proto/
```
(편집 설치라 `schema/`·`prompt/` 가 `/app/assistant_proto/` 에 있어야 런타임에 읽힌다.)

`.dockerignore` — 첫 주석과 허용 목록·제외 목록:
```gitignore
# 이미지에는 server/ 와 lora_proto/ · assistant_proto/ 만 들어간다 (server/Dockerfile).
*
!server/
!lora_proto/
!assistant_proto/
```
그리고 맨 아래 `lora_proto/tests/` 다음 줄에:
```gitignore
assistant_proto/tests/
```

- [ ] **Step 4: CI 필터·스모크**

`.github/workflows/ci.yml`:
- `filters:` 의 `server:` 와 `docker:` 블록에 각각 `- 'assistant_proto/**'` 를 추가한다.
- `docker` job 스모크 스텝 끝(`Server 헤더` 검사 앞)에 두 줄:
```yaml
          docker exec esc-server python -c "import assistant_proto as A; assert A.json_schema()['properties']['v'] == {'const': 1} and A.SYSTEM_PROMPT"  # 규격 데이터 파일이 이미지에 있다
          curl -fsS http://localhost:8000/api/assistant/model -H "Authorization: Bearer $T" | grep -q '"enabled":false'  # AI 비서 — 모델 안내 기본은 꺼짐
```
(`/api/assistant/model` 은 Task 14 에서 생긴다. 이 PR 안에서 함께 머지되므로 PR B 의 CI 에서 처음 돈다.)

- [ ] **Step 5: 통과 + 커밋**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (기존 테스트 전부 + 새 1개). Docker Desktop 이 있으면 리포 루트에서 `docker compose build` 로 이미지가 빌드되는지 확인(없으면 CI `docker` job 이 확인).

```bash
git add server/pyproject.toml server/uv.lock server/Dockerfile .dockerignore .github/workflows/ci.yml \
  server/tests/test_assistant_proto_dep.py
git commit -m "chore(infra): 서버가 assistant_proto 를 경로 의존 — Docker 이미지·CI 필터·스모크"
```

---

### Task 6: 커밋하지 않는 쓰기 — `app/domain/ops.py` (wj 리뷰)

**Files:**
- Create: `server/app/domain/ops.py`
- Modify: `server/app/domain/router.py` (import 2줄, `_put_slot` 삭제, 라우트 6곳 본문)
- Test: `server/tests/test_domain_ops.py`

**Interfaces:**
- Produces (`app.domain.ops`):
  - `room_addr(s, room_id) -> tuple[str, int, str | None]` — (bld, room, modem_id), 범위 검사 없음
  - `put_slot(s, room_id, bld, room, body: S.SlotIn) -> list[int]` — source 보호 409
  - `delete_slot(s, room_id, bld, room, day, s_h, s_m) -> list[int]`
  - `clear_day(s, room_id, bld, room, day) -> list[int]`
  - `write_resv(s, room_id, body: S.ResvIn, rid: int, obj: Reservation | None, now_local) -> list[int]` — 창 안이면 용량 409 + RESV_SET, 창 밖이면 옛 항목 RESV_DEL
  - `delete_resv(s, room_id, resv_id, now_local) -> list[int] | None` — 없거나 다른 방이면 `None`
  - `write_exam(s, room_id, bld, room, body: S.ExamIn, eid: int, obj: ExamPeriod | None) -> list[int]`
  - `delete_exam(s, room_id, bld, room, exam_id) -> list[int]`
  - 모두 **커밋·notify 하지 않는다**. `_ID_LOCK`·채번은 호출자(router 그대로).
- 승인·거절은 이미 커밋하지 않는 `reserve.approve`·`reserve.reject` 를 그대로 쓴다(손대지 않음).

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_domain_ops.py`:
```python
import datetime as dt

from sqlalchemy import func, select

from app import schemas as S
from app.domain import ops
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service.models import Outbox, RoomVersion

NOW = dt.datetime(2026, 11, 25, 10, 0)  # noqa: DTZ001 — KST naive (ops 는 지역 시각을 받는다)
SLOT = S.SlotIn(day=1, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="자료구조", professor="김")
RESV = S.ResvIn(
    date=dt.date(2026, 11, 27), s_h=15, s_m=0, e_h=18, e_m=0, type=5, subject="특강", professor=""
)
EXAM = S.ExamIn(date_start=dt.date(2026, 12, 15), date_end=dt.date(2026, 12, 19))


def _room(db) -> int:
    """FakeTopo 의 E301(유닛 2, 모뎀 m1) 과 같은 방을 DB 에 — enqueue 가 유닛마다 행을 만든다."""
    with db() as s, s.begin():
        b = Building(school_id=1, name="E동", bld="E")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=301, units=2)
        s.add(r)
        s.flush()
        return r.id


def _n(s, model) -> int:
    return s.scalar(select(func.count()).select_from(model))


def test_writes_flush_but_do_not_commit(app, school, db):
    rid = _room(db)
    with db() as s:
        assert ops.room_addr(s, rid) == ("E", 301, None)
        ids = ops.put_slot(s, rid, "E", 301, SLOT)
        ids += ops.write_resv(s, rid, RESV, 1, None, NOW)
        ids += ops.write_exam(s, rid, "E", 301, EXAM, 1, None)
        s.flush()
        assert len(ids) == 6  # 3 작업 × 유닛 2
        assert (_n(s, Slot), _n(s, Reservation), _n(s, ExamPeriod)) == (1, 1, 1)
        s.rollback()
    with db() as s:  # rollback 하면 도메인 행도 outbox·버전도 남지 않는다
        assert (_n(s, Slot), _n(s, Reservation), _n(s, ExamPeriod)) == (0, 0, 0)
        assert _n(s, Outbox) == 0 and _n(s, RoomVersion) == 0


def test_deletes_and_idempotent_resv(app, school, db):
    rid = _room(db)
    with db() as s, s.begin():
        ops.put_slot(s, rid, "E", 301, SLOT)
        ops.write_resv(s, rid, RESV, 1, None, NOW)
        ops.write_exam(s, rid, "E", 301, EXAM, 1, None)
    with db() as s, s.begin():
        assert ops.delete_resv(s, rid, 99, NOW) is None  # 없는 id — RESV_DEL 안 보냄
        assert len(ops.delete_resv(s, rid, 1, NOW)) == 2  # 노드로 보낸 예약 → RESV_DEL × 유닛 2
        assert len(ops.delete_slot(s, rid, "E", 301, 1, 9, 0)) == 2
        assert len(ops.delete_exam(s, rid, "E", 301, 1)) == 2
        assert len(ops.clear_day(s, rid, "E", 301, 2)) == 2
    with db() as s:
        assert (_n(s, Slot), _n(s, Reservation), _n(s, ExamPeriod)) == (0, 0, 0)
```

Run: `uv run pytest tests/test_domain_ops.py -q`
Expected: FAIL — `ImportError: cannot import name 'ops' from 'app.domain'`.

- [ ] **Step 2: `ops.py`**

`server/app/domain/ops.py`:
```python
"""도메인 쓰기 — 커밋·notify 를 하지 않는다 (AI 비서 spec §5.1).

관리자 라우터 = 이 함수 + 커밋 + notify. AI 비서 미리보기 = 이 함수 + rollback, 적용 = 이 함수 + 커밋 + notify.
그래서 미리보기에서 본 결과와 실제 적용 결과가 같은 코드에서 나온다.

채번(_free_id)·같은 방 검사(_existing_same_room)·ID_MAX·_ID_LOCK 은 router 에 그대로 둔다 —
tests/test_admin_ids.py 가 router 모듈 속성을 바꿔 끼운다. _ID_LOCK 은 호출자가 잡는다."""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import schemas as S
from app.domain import reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot
from app.lora_service import api


def room_addr(s: Session, room_id: int) -> tuple[str, int, str | None]:
    """(bld, room, modem_id). 범위 검사는 호출자가 먼저 한다."""
    r = s.get(Room, room_id)
    b = s.get(Building, r.building_id)
    return b.bld, r.room, b.modem_id


def put_slot(s: Session, room_id: int, bld: str, room: int, body: S.SlotIn) -> list[int]:
    """슬롯 한 개 쓰기 + outbox (옛 router._put_slot 그대로)."""
    obj = s.scalar(
        select(Slot).where(
            Slot.room_id == room_id,
            Slot.day == body.day,
            Slot.s_h == body.s_h,
            Slot.s_m == body.s_m,
        )
    )
    if obj is not None and obj.source > body.source:
        raise HTTPException(409, f"source {obj.source} 슬롯은 source ≥ {obj.source} 로만 수정")
    if obj is None:
        obj = Slot(room_id=room_id)
        s.add(obj)
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    return api.enqueue_slot_set(
        bld,
        room,
        body.day,
        (body.s_h, body.s_m),
        (body.e_h, body.e_m),
        body.type,
        body.subject,
        body.professor,
        session=s,
    )


def delete_slot(
    s: Session, room_id: int, bld: str, room: int, day: int, s_h: int, s_m: int
) -> list[int]:
    s.execute(
        delete(Slot).where(
            Slot.room_id == room_id, Slot.day == day, Slot.s_h == s_h, Slot.s_m == s_m
        )
    )
    return api.enqueue_slot_del(bld, room, day, (s_h, s_m), session=s)


def clear_day(s: Session, room_id: int, bld: str, room: int, day: int) -> list[int]:
    s.execute(delete(Slot).where(Slot.room_id == room_id, Slot.day == day))
    return api.enqueue_day_clear(bld, room, day, session=s)


def write_resv(
    s: Session,
    room_id: int,
    body: S.ResvIn,
    rid: int,
    obj: Reservation | None,
    now_local: dt.datetime,
) -> list[int]:
    """예약 쓰기 (옛 router._write_resv 에서 커밋·notify 를 뺀 것)."""
    obj = obj or Reservation(id=rid, room_id=room_id)
    old_end = (obj.date, obj.e_h, obj.e_m)  # 노드가 가진 옛 항목의 끝 (새 행이면 None 들)
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(obj, k, v)
    s.add(obj)
    today = now_local.date()
    if reserve.in_window(body.date, today):
        if reserve.room_full(s, room_id, today, exclude_id=rid):
            raise HTTPException(409, "이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)")
        return reserve.push_set(s, obj)
    # 창 밖으로 옮겼으면 노드의 옛 날짜 항목을 지운다 (r3, 리뷰 🔴1c)
    return reserve.push_del(s, obj, now_local, end=old_end if old_end[0] else None)


def delete_resv(
    s: Session, room_id: int, resv_id: int, now_local: dt.datetime
) -> list[int] | None:
    """없거나 다른 방 행이면 None — 멱등, 없는 id 에 RESV_DEL 을 보내지 않는다."""
    r = s.get(Reservation, resv_id)
    if r is None or r.room_id != room_id:
        return None
    ids = reserve.push_del(s, r, now_local)  # 노드로 보낸 적 있는 것만 (r2)
    s.delete(r)
    return ids


def write_exam(
    s: Session,
    room_id: int,
    bld: str,
    room: int,
    body: S.ExamIn,
    eid: int,
    obj: ExamPeriod | None,
) -> list[int]:
    obj = obj or ExamPeriod(id=eid, room_id=room_id)
    obj.date_start, obj.date_end = body.date_start, body.date_end
    s.add(obj)
    return api.enqueue_exam_set(bld, room, eid, body.date_start, body.date_end, session=s)


def delete_exam(s: Session, room_id: int, bld: str, room: int, exam_id: int) -> list[int]:
    s.execute(delete(ExamPeriod).where(ExamPeriod.id == exam_id, ExamPeriod.room_id == room_id))
    return api.enqueue_exam_del(bld, room, exam_id, session=s)
```

- [ ] **Step 3: 라우터가 `ops` 를 쓰게 (동작 불변)**

`server/app/domain/router.py`:

1. import 두 줄을 바꾼다 (`delete`·`reserve` 는 더 쓰지 않는다):
```python
from sqlalchemy import select
```
```python
from app.domain import admin, clock, csv_import, ops
```
2. `def _put_slot(...)` 함수 전체를 지운다.
3. `put_slot` 라우트 본문의 `ids = _put_slot(s, id, bld, room, body)` → `ids = ops.put_slot(s, id, bld, room, body)`.
4. `replace_slots` 의 반복문 두 개를:
```python
    for k in body.remove:
        if (k.day, k.s_h, k.s_m) in keep:
            continue
        ids += ops.delete_slot(s, id, bld, room, k.day, k.s_h, k.s_m)
    for p in body.put:
        ids += ops.put_slot(s, id, bld, room, p)
```
5. `delete_slot` 라우트 본문:
```python
    bld, room, mid = _addr(s, id, sc)
    ids = ops.delete_slot(s, id, bld, room, day, s_h, s_m)
    _commit_notify(s, mid)
    return {"outbox_ids": ids}
```
6. `clear_day` 라우트 본문:
```python
    bld, room, mid = _addr(s, id, sc)
    ids = ops.clear_day(s, id, bld, room, day)
    _commit_notify(s, mid)
    return {"outbox_ids": ids}
```
7. `_write_resv` 를 (시그니처 그대로):
```python
def _write_resv(
    s, room_id, bld, room, mid, body: S.ResvIn, rid: int, obj: Reservation | None
) -> dict:
    ids = ops.write_resv(s, room_id, body, rid, obj, clock.local_now())
    _commit_notify(s, mid)
    return {"outbox_ids": ids, "id": rid}
```
8. `delete_resv` 라우트 본문:
```python
    *_, mid = _addr(s, id, sc)
    with _ID_LOCK:  # 예약 쓰기는 읽기~커밋 전부 같은 락 — 동시 승인·승격과 엇갈리지 않게
        ids = ops.delete_resv(s, id, resv_id, clock.local_now())
        if ids is None:  # 멱등 — 없는 id 에 RESV_DEL 을 보내지 않는다
            return {"outbox_ids": []}
        _commit_notify(s, mid)
    return {"outbox_ids": ids}
```
9. `_write_exam` 을 (시그니처 그대로):
```python
def _write_exam(
    s, room_id, bld, room, mid, body: S.ExamIn, eid: int, obj: ExamPeriod | None
) -> dict:
    ids = ops.write_exam(s, room_id, bld, room, body, eid, obj)
    _commit_notify(s, mid)
    return {"outbox_ids": ids, "id": eid}
```
10. `delete_exam` 라우트 본문:
```python
    bld, room, mid = _addr(s, id, sc)
    with _ID_LOCK:  # 같은 id 수정(put_exam)의 읽기~커밋 사이에 끼어들면 StaleDataError (#48 🟡2)
        ids = ops.delete_exam(s, id, bld, room, exam_id)
        _commit_notify(s, mid)
    return {"outbox_ids": ids}
```

- [ ] **Step 4: 통과 — 기존 테스트 무수정**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS. **`git diff --stat -- tests/` 에 기존 테스트 파일이 하나도 없어야 한다**(새 파일 `test_domain_ops.py` 만). 기존 테스트가 하나라도 실패하면 테스트가 아니라 `ops.py`/라우터를 고친다.

```bash
git add server/app/domain/ops.py server/app/domain/router.py server/tests/test_domain_ops.py
git commit -m "refactor(server): 커밋하지 않는 쓰기를 domain/ops.py 로 — 라우터 동작 불변 (AI 비서 미리보기·적용 공용)"
```

---

### Task 7: 표 4개 — 모델 + 마이그레이션

**Files:**
- Create: `server/app/assistant/__init__.py`, `server/app/assistant/models.py`, `server/alembic/versions/web_assistant_a7c3e91d5f20.py`
- Modify: `server/alembic/env.py` (import 한 줄)
- Test: `server/tests/test_assistant_migration.py`

**Interfaces:**
- Produces: `AssistantConversation`, `AssistantTurn`, `AssistantPreview`, `AssistantChange` (아래 컬럼 그대로). 시각은 naive UTC.

| 표 | 컬럼 |
|---|---|
| `assistant_conversations` | `id` str PK(`c_`+16hex) · `user_email` FK users CASCADE · `state` text(JSON, 닫히면 `null`) · `created_at` · `updated_at` · `closed_at`? |
| `assistant_turns` | `id` int PK · `conversation_id` · `user_email` · `utterance` · `form`?(JSON) · `choice`? · `reply_kind` · `reply_message` · `model_rev`? · `created_at` |
| `assistant_previews` | `id` str PK(`p_`+16hex) · `conversation_id` · `user_email` · `draft`(JSON) · `ops`(JSON) · `room_ids`(JSON) · `fingerprint` · `blockers`(JSON) · `summary`(JSON) · `created_at` · `expires_at` · `applied_at`? |
| `assistant_changes` | `id` int PK · `preview_id` · `user_email` · `school_id` · `building_ids`(JSON) · `utterance` · `ops`(JSON) · `summary`(JSON) · `outbox_ids`(JSON) · `model_rev`? · `applied_at` |

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_migration.py`:
```python
from sqlalchemy import create_engine, inspect

from app.db import Base
from tests.test_migrations import _upgrade

TABLES = ("assistant_conversations", "assistant_turns", "assistant_previews", "assistant_changes")


def test_web_assistant_migration_creates_tables(tmp_path):
    names = _upgrade(tmp_path / "ai.db")
    assert set(TABLES) <= names


def test_models_match_migration(tmp_path):
    import app.assistant.models  # noqa: F401 — Base.metadata 에 등록

    db = tmp_path / "m.db"
    _upgrade(db)
    insp = inspect(create_engine(f"sqlite:///{db}"))
    for t in TABLES:
        migrated = {c["name"]: c["nullable"] for c in insp.get_columns(t)}
        model = {c.name: c.nullable for c in Base.metadata.tables[t].columns}
        assert migrated == model, t
```

Run: `uv run pytest tests/test_assistant_migration.py -q`
Expected: FAIL — 표 없음 / `ModuleNotFoundError: app.assistant`.

- [ ] **Step 2: 모델**

`server/app/assistant/__init__.py`:
```python
"""관리자 AI 비서 (docs/specs/2026-11-25-admin-ai-assistant-design.md). 담당 cw."""
```

`server/app/assistant/models.py`:
```python
"""AI 비서 표 (spec §5.5·§9). 마이그레이션 web_assistant_*. 시각은 naive UTC (app.db.utcnow).
JSON 칸은 Text 에 json.dumps(ensure_ascii=False) 로 넣는다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # "c_" + 16 hex
    user_email: Mapped[str] = mapped_column(ForeignKey("users.email", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(Text)  # dialog 상태 JSON, 닫히면 "null"
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    closed_at: Mapped[dt.datetime | None]
    __table_args__ = (Index("ix_assistant_conv_updated", "updated_at"),)


class AssistantTurn(Base):
    """학습용 대화 기록 — 서버에만, 180일 뒤 지운다 (spec §5.5)."""

    __tablename__ = "assistant_turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String)
    user_email: Mapped[str] = mapped_column(String)
    utterance: Mapped[str] = mapped_column(Text)
    form: Mapped[str | None] = mapped_column(Text)  # 모델 출력 JSON (못 읽은 출력은 원문, 버튼 선택 턴은 NULL)
    choice: Mapped[str | None] = mapped_column(String)
    reply_kind: Mapped[str] = mapped_column(String)
    reply_message: Mapped[str] = mapped_column(Text)
    model_rev: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    __table_args__ = (Index("ix_assistant_turns_created", "created_at"),)


class AssistantPreview(Base):
    __tablename__ = "assistant_previews"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # "p_" + 16 hex
    conversation_id: Mapped[str] = mapped_column(String)
    user_email: Mapped[str] = mapped_column(String)
    draft: Mapped[str] = mapped_column(Text)  # 해석이 끝난 초안 — 지문이 바뀌면 이것으로 다시 미리보기
    ops: Mapped[str] = mapped_column(Text)  # 확정 변경 목록 — 적용은 이것만 실행한다
    room_ids: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String)
    blockers: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[dt.datetime]
    applied_at: Mapped[dt.datetime | None]
    __table_args__ = (Index("ix_assistant_previews_expires", "expires_at"),)


class AssistantChange(Base):
    __tablename__ = "assistant_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    preview_id: Mapped[str] = mapped_column(String)
    user_email: Mapped[str] = mapped_column(String)
    school_id: Mapped[int]
    building_ids: Mapped[str] = mapped_column(Text)  # 건물 관리자 목록 범위 거르기
    utterance: Mapped[str] = mapped_column(Text)
    ops: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    outbox_ids: Mapped[str] = mapped_column(Text)
    model_rev: Mapped[str | None] = mapped_column(String)
    applied_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    __table_args__ = (Index("ix_assistant_changes_school", "school_id", "applied_at"),)
```

`server/alembic/env.py` — 모델 import 줄 묶음에 추가:
```python
import app.assistant.models
```
(기존 `import app.lora_service.models  # noqa: F401` 위. ruff 가 정렬하면 따른다.)

- [ ] **Step 3: 마이그레이션**

`server/alembic/versions/web_assistant_a7c3e91d5f20.py`:
```python
"""web_assistant — 관리자 AI 비서 대화·턴 기록·미리보기·변경 기록

(docs/specs/2026-11-25-admin-ai-assistant-design.md §9). 새 표만 — 기존 표 불변.

Revision ID: a7c3e91d5f20
Revises: 5e2a91c7d3b4
Create Date: 2026-11-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c3e91d5f20"
down_revision: str | Sequence[str] | None = "5e2a91c7d3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_email",
            sa.String(),
            sa.ForeignKey("users.email", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_assistant_conv_updated", "assistant_conversations", ["updated_at"])
    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("form", sa.Text(), nullable=True),
        sa.Column("choice", sa.String(), nullable=True),
        sa.Column("reply_kind", sa.String(), nullable=False),
        sa.Column("reply_message", sa.Text(), nullable=False),
        sa.Column("model_rev", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_assistant_turns_created", "assistant_turns", ["created_at"])
    op.create_table(
        "assistant_previews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("draft", sa.Text(), nullable=False),
        sa.Column("ops", sa.Text(), nullable=False),
        sa.Column("room_ids", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("blockers", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_assistant_previews_expires", "assistant_previews", ["expires_at"])
    op.create_table(
        "assistant_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preview_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("building_ids", sa.Text(), nullable=False),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("ops", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("outbox_ids", sa.Text(), nullable=False),
        sa.Column("model_rev", sa.String(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_assistant_changes_school", "assistant_changes", ["school_id", "applied_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_changes_school", table_name="assistant_changes")
    op.drop_table("assistant_changes")
    op.drop_index("ix_assistant_previews_expires", table_name="assistant_previews")
    op.drop_table("assistant_previews")
    op.drop_index("ix_assistant_turns_created", table_name="assistant_turns")
    op.drop_table("assistant_turns")
    op.drop_index("ix_assistant_conv_updated", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
```

- [ ] **Step 4: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_migration.py tests/test_migrations.py -q && uv run pytest -q`
Expected: PASS. (`test_models_match_migration` 이 실패하면 컬럼 이름·nullable 을 모델과 마이그레이션에서 맞춘다.)

```bash
git add server/app/assistant/__init__.py server/app/assistant/models.py server/alembic/env.py \
  server/alembic/versions/web_assistant_a7c3e91d5f20.py server/tests/test_assistant_migration.py
git commit -m "feat(server): AI 비서 표 4개 — 대화·턴 기록·미리보기·변경 기록 (web_assistant 마이그레이션)"
```

---

### Task 8: 강의실 표현 → 방 (DB · 건물 범위)

**Files:**
- Create: `server/app/assistant/rooms.py`, `server/tests/assistant_util.py`
- Test: `server/tests/test_assistant_rooms.py`

**Interfaces:**
- Consumes: `assistant_proto.normalize_room`, `scope.building_clause`
- Produces (`app.assistant.rooms`):
  - `RoomRef(id, building_id, building, bld, room)` + `.label` = `"공학관 803"`
  - `Found(rooms: tuple[RoomRef, ...])`, `Ambiguous(expr, options: tuple[tuple[str, str], ...])` — 선택지 id `"room:{room_id}"`(한 방) 또는 `"bld:{building_id}"`(범위·층·건물), `Missing(expr)`
  - `scoped_rooms(s, sc) -> list[RoomRef]` (건물 id, 호수 순)
  - `resolve_room_expr(s, sc, expr, *, only_building: int | None = None) -> Found | Ambiguous | Missing`
- 규칙: `"803"`(호수) · `"공학관 803"`·`"E동 803"`(건물+호수) · `"801~805"`(범위) · `"8층"`·`"8층 전체"`(층 = 호수//100) · `"공학관"`(건물 전체) · `"공학관 8층 전체"`. 호수가 여러 건물에 있으면 방 선택지, 범위·층이 여러 건물에 걸치면 건물 선택지.

- [ ] **Step 1: 테스트 도우미**

`server/tests/assistant_util.py`:
```python
"""AI 비서 테스트 도우미 — 이름이 test_ 로 시작하지 않아 pytest 가 수집하지 않는다."""

import datetime as dt

from app.auth import password
from app.auth.models import User, UserBuilding
from app.auth.scope import Scope
from app.domain import clock
from app.domain.models import Building, Reservation, Room, Slot

UTC_NOW = dt.datetime(2026, 11, 25, 1, 0)  # noqa: DTZ001 — KST 11/25(수) 10:00
NOW = dt.datetime(2026, 11, 25, 10, 0)  # noqa: DTZ001 — 같은 시각, KST naive
ALL = Scope(1, None, "admin@mju.ac.kr")


def fix_clock(monkeypatch, utc: dt.datetime = UTC_NOW) -> None:
    monkeypatch.setattr(clock, "now_utc", lambda: utc)


def campus(app) -> dict[str, int]:
    """학교 1: 공학관(E) 301·801·802·803·805, 인문관(H) 201·803. 학교 2: 타교관(Z) 803.
    공학관 803 정규 수업: 월 09:00–12:00 알고리즘(이), 금 15:00–16:15 자료구조(김)."""
    ids: dict[str, int] = {}
    with app.state.Session() as s, s.begin():
        for school_id, name, bld, rooms in (
            (1, "공학관", "E", (301, 801, 802, 803, 805)),
            (1, "인문관", "H", (201, 803)),
            (2, "타교관", "Z", (803,)),
        ):
            b = Building(school_id=school_id, name=name, bld=bld)
            s.add(b)
            s.flush()
            ids[bld] = b.id
            for n in rooms:
                r = Room(building_id=b.id, room=n, units=1)
                s.add(r)
                s.flush()
                ids[f"{bld}{n}"] = r.id
        s.add_all(
            [
                Slot(room_id=ids["E803"], day=1, s_h=9, s_m=0, e_h=12, e_m=0, type=1,
                     subject="알고리즘", professor="이"),
                Slot(room_id=ids["E803"], day=5, s_h=15, s_m=0, e_h=16, e_m=15, type=1,
                     subject="자료구조", professor="김"),
            ]
        )
    return ids


def resv(app, room_id, date, start, end, *, id_, type_=5, subject="특강", status="approved",
         requested_by=None) -> int:
    """start·end = (시, 분)."""
    with app.state.Session() as s, s.begin():
        s.add(
            Reservation(
                id=id_, room_id=room_id, date=date, s_h=start[0], s_m=start[1], e_h=end[0],
                e_m=end[1], type=type_, subject=subject, professor="", status=status,
                requested_by=requested_by, requested_at=UTC_NOW if requested_by else None,
            )
        )
    return id_


def building_admin(app, email: str, building_ids: list[int]) -> None:
    with app.state.Session() as s, s.begin():
        s.add(
            User(email=email, school_id=1, role="building_admin", status="active",
                 name="건물관리", pw_hash=password.hash("adminpass1"))
        )
        s.flush()
        s.add_all([UserBuilding(email=email, building_id=b) for b in building_ids])


def form(intent: str, target: dict | None = None, set_: dict | None = None) -> dict:
    return {"v": 1, "intent": intent, "target": target or {}, "set": set_ or {}}


def turn(client, utterance, form_=None, *, conv=None, choice=None, headers=None) -> dict:
    r = client.post(
        "/api/assistant/turns",
        json={"conversation_id": conv, "utterance": utterance, "form": form_, "choice": choice},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()
```

- [ ] **Step 2: 실패하는 테스트**

`server/tests/test_assistant_rooms.py`:
```python
import pytest

from app.assistant import rooms as R
from app.auth.scope import Scope
from tests.assistant_util import ALL, campus


def _resolve(app, expr, sc=ALL, **kw):
    with app.state.Session() as s:
        return R.resolve_room_expr(s, sc, expr, **kw)


def test_number_in_two_buildings_asks_room(app, school):
    ids = campus(app)
    got = _resolve(app, "803호")
    assert got == R.Ambiguous(
        "803호", ((f"room:{ids['E803']}", "공학관 803"), (f"room:{ids['H803']}", "인문관 803"))
    )


def test_building_admin_scope_narrows(app, school):
    ids = campus(app)
    only_e = Scope(1, frozenset({ids["E"]}), "b@mju.ac.kr")
    got = _resolve(app, "803", only_e)
    assert isinstance(got, R.Found) and [r.id for r in got.rooms] == [ids["E803"]]
    assert got.rooms[0].label == "공학관 803"
    assert isinstance(_resolve(app, "인문관 803", only_e), R.Missing)


@pytest.mark.parametrize(
    ("expr", "want"),
    [
        ("공학관 803", ["E803"]),
        ("E동 803", ["E803"]),
        ("801~803", ["E801", "E802", "E803"]),
        ("801호 ~ 803호", ["E801", "E802", "E803"]),
        ("공학관 8층 전체", ["E801", "E802", "E803", "E805"]),
        ("공학관", ["E301", "E801", "E802", "E803", "E805"]),
        ("인문관 2층", ["H201"]),
    ],
)
def test_found(app, school, expr, want):
    ids = campus(app)
    got = _resolve(app, expr)
    assert isinstance(got, R.Found) and [r.id for r in got.rooms] == [ids[k] for k in want]


def test_floor_across_buildings_asks_building(app, school):
    ids = campus(app)
    got = _resolve(app, "8층")
    assert got == R.Ambiguous(
        "8층", ((f"bld:{ids['E']}", "공학관 8층 (4개)"), (f"bld:{ids['H']}", "인문관 8층 (1개)"))
    )
    got = _resolve(app, "8층", only_building=ids["E"])
    assert [r.id for r in got.rooms] == [ids[k] for k in ("E801", "E802", "E803", "E805")]


@pytest.mark.parametrize("expr", ["999", "체육관 803", "어딘가", "Z동 803", "타교관 803"])
def test_missing(app, school, expr):
    campus(app)
    assert _resolve(app, expr) == R.Missing(expr)  # 다른 학교(Z) 방은 없는 것과 같다
```

Run: `uv run pytest tests/test_assistant_rooms.py -q`
Expected: FAIL — `ImportError: cannot import name 'rooms' from 'app.assistant'`.

- [ ] **Step 3: 구현**

`server/app/assistant/rooms.py`:
```python
"""강의실 표현 → 방 (spec §4). 범위(scope) 안 방만 본다 — 범위 밖·다른 학교 방은 없는 것과 같다."""

from __future__ import annotations

import re
from dataclasses import dataclass

from assistant_proto import normalize_room
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import scope
from app.auth.scope import Scope
from app.domain.models import Building, Room

_SPLIT = re.compile(r"^(?P<b>[^\d]*?)\s*(?P<rest>\d.*)?$")  # 건물 이름(숫자 아님) + 나머지
_NUM = re.compile(r"^(\d{1,4})$")
_RANGE = re.compile(r"^(\d{1,4})[~\-](\d{1,4})$")
_FLOOR = re.compile(r"^(\d{1,2})층(?:전체)?$")


@dataclass(frozen=True)
class RoomRef:
    id: int
    building_id: int
    building: str
    bld: str
    room: int

    @property
    def label(self) -> str:
        return f"{self.building} {self.room}"


@dataclass(frozen=True)
class Found:
    rooms: tuple[RoomRef, ...]


@dataclass(frozen=True)
class Ambiguous:
    expr: str
    options: tuple[tuple[str, str], ...]  # (선택지 id, 라벨)


@dataclass(frozen=True)
class Missing:
    expr: str


def scoped_rooms(s: Session, sc: Scope) -> list[RoomRef]:
    q = (
        select(Room, Building)
        .join(Building, Room.building_id == Building.id)
        .where(scope.building_clause(sc))
        .order_by(Building.id, Room.room)
    )
    return [RoomRef(r.id, b.id, b.name, b.bld, r.room) for r, b in s.execute(q).all()]


def _bkey(x: str) -> str:
    return x.replace(" ", "").removesuffix("동")


def resolve_room_expr(
    s: Session, sc: Scope, expr: str, *, only_building: int | None = None
) -> Found | Ambiguous | Missing:
    m = _SPLIT.match(normalize_room(expr))
    if m is None:
        return Missing(expr)
    bexpr, rest = m.group("b").strip(), (m.group("rest") or "").strip()
    compact = rest.replace(" ", "")
    refs = scoped_rooms(s, sc)
    if only_building is not None:
        refs = [r for r in refs if r.building_id == only_building]
    if bexpr:
        k = _bkey(bexpr)
        refs = [
            r
            for r in refs
            if k and (k == _bkey(r.building) or k == r.bld or _bkey(r.building).startswith(k))
        ]
    if not compact:  # 건물 이름만 — 그 건물 전체
        hits, many = (refs if bexpr else []), True
    elif mm := _NUM.match(compact):
        hits, many = [r for r in refs if r.room == int(mm.group(1))], False
    elif mm := _RANGE.match(compact):
        a, b = sorted((int(mm.group(1)), int(mm.group(2))))
        hits, many = [r for r in refs if a <= r.room <= b], True
    elif mm := _FLOOR.match(compact):
        hits, many = [r for r in refs if r.room // 100 == int(mm.group(1))], True
    else:
        return Missing(expr)
    if not hits:
        return Missing(expr)
    blds = list(dict.fromkeys(r.building_id for r in hits))
    if len(blds) == 1:
        return Found(tuple(hits))
    if not many:
        return Ambiguous(expr, tuple((f"room:{r.id}", r.label) for r in hits))
    names = {r.building_id: r.building for r in hits}
    return Ambiguous(
        expr,
        tuple(
            (f"bld:{b}", f"{names[b]} {rest} ({sum(r.building_id == b for r in hits)}개)")
            for b in blds
        ),
    )
```

- [ ] **Step 4: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_rooms.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (ruff format 이 `assistant_util.py` 를 다시 쓰면 그대로 둔다).

```bash
git add server/app/assistant/rooms.py server/tests/assistant_util.py server/tests/test_assistant_rooms.py
git commit -m "feat(server): AI 비서 강의실 해석 — 호수·건물·범위·층, 건물 범위 안에서만"
```

---

### Task 9: 대화 상태 — 반영(absorb) · 선택(choose)

**Files:**
- Create: `server/app/assistant/dialog.py`
- Test: `server/tests/test_assistant_dialog.py`

**Interfaces:**
- Consumes: `assistant_proto.Form`·`form_to_dict`·`TYPE_LABELS`·`rules.PRIMARY`
- Produces (`app.assistant.dialog`):
  - 상태 dict: `{"intent", "target", "set", "room_pick", "pick", "asked", "pending", "utterances"}`
    - `target`·`set` = 양식의 칸(표현 그대로) · `room_pick` = `{"set:803": {"ids": [7]} | {"building": 2}}` · `pick` = `{"<room_id>": "<후보 key>"}` · `asked` = `"set.subject"` · `pending` = `{"kind": "room"|"pick"|"type", "options": [선택지 id...], …}`
  - `new_state(form_dict, utterance) -> dict`
  - `absorb(state | None, form: Form, utterance) -> tuple[dict | None, str]` — `(새 상태, 앞에 붙일 안내)`. `cancel` → `(None, "취소했습니다.")`. `unknown` → `Unsupported`. 대화 없이 `fill` → `NeedContext`. 새 작업 → 안내 `"앞의 요청은 그만두고 새로 시작합니다. "`
  - `choose(state | None, choice, utterance) -> dict` — 내놓은 선택지(`pending.options`)가 아니면 `NeedContext`
  - `TYPE_CHOICES`, 예외 `Unsupported`·`NeedContext`, 결과 `Ask(question, state, choices)`·`Fail(message, state)`·`Ready(draft, state)`·`Answer(draft)` (Task 10 의 `advance` 가 돌려준다)

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_dialog.py`:
```python
import pytest
from assistant_proto import parse_form

from app.assistant import dialog as D


def F(intent, target=None, set_=None):
    return parse_form({"v": 1, "intent": intent, "target": target or {}, "set": set_ or {}})


def test_new_request_starts_state():
    st, lead = D.absorb(None, F("event.add", set_={"rooms": ["803"]}), "803 특강")
    assert lead == ""
    assert st == {
        "intent": "event.add",
        "target": {},
        "set": {"rooms": ["803"]},
        "room_pick": {},
        "pick": {},
        "asked": None,
        "pending": None,
        "utterances": ["803 특강"],
    }


def test_cancel_unknown_and_fill_without_state():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {}}, "u")
    assert D.absorb(st, F("cancel"), "취소") == (None, "취소했습니다.")
    with pytest.raises(D.Unsupported):
        D.absorb(st, F("unknown"), "안녕")
    with pytest.raises(D.NeedContext):
        D.absorb(None, F("fill", set_={"subject": "x"}), "x")


def test_fill_goes_to_asked_section_and_rooms_accumulate():
    st = D.new_state({"intent": "event.change", "target": {"rooms": ["803"]}, "set": {}}, "u1")
    st["asked"] = "target.when"
    st2, lead = D.absorb(st, F("fill", set_={"when": "금요일"}), "금요일")
    assert lead == "" and st2["target"] == {"rooms": ["803"], "when": "금요일"} and st2["set"] == {}
    assert st2["asked"] is None and st2["utterances"] == ["u1", "금요일"]
    assert st["target"] == {"rooms": ["803"]}  # 원본은 그대로(깊은 복사)

    add = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803"]}}, "u")
    add2, _ = D.absorb(add, F("fill", set_={"rooms": ["801", "803"]}), "801도")
    assert add2["set"]["rooms"] == ["803", "801"]

    # 묻는 칸이 없으면 intent 의 기본 묶음 — 수정은 새 값(set)
    ch = D.new_state({"intent": "event.change", "target": {"rooms": ["803"]}, "set": {}}, "u")
    ch2, _ = D.absorb(ch, F("fill", set_={"time": "16시"}), "16시로")
    assert ch2["set"] == {"time": "16시"}


def test_fill_after_room_question_replaces_ambiguous_expr():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803", "801"]}}, "u")
    st["asked"] = "set.rooms"
    st["pending"] = {"kind": "room", "key": "set:803", "section": "set", "expr": "803",
                     "options": ["room:1", "room:2"]}
    st2, _ = D.absorb(st, F("fill", set_={"rooms": ["공학관 803"]}), "공학관 803")
    assert st2["set"]["rooms"] == ["801", "공학관 803"] and st2["pending"] is None


def test_new_intent_replaces_with_notice():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803"]}}, "u")
    st2, lead = D.absorb(st, F("ask.requests"), "신청 보여줘")
    assert lead == "앞의 요청은 그만두고 새로 시작합니다. "
    assert st2["intent"] == "ask.requests" and st2["utterances"] == ["신청 보여줘"]


def test_choose_only_offered_options():
    st = D.new_state({"intent": "event.add", "target": {}, "set": {"rooms": ["803"]}}, "u")
    with pytest.raises(D.NeedContext):
        D.choose(st, "room:7", "x")  # 내놓은 선택지 없음
    st["pending"] = {"kind": "room", "key": "set:803", "section": "set", "expr": "803",
                     "options": ["room:7", "room:8"]}
    st["asked"] = "set.rooms"
    with pytest.raises(D.NeedContext):
        D.choose(st, "room:9", "x")
    st2 = D.choose(st, "room:7", "공학관 803")
    assert st2["room_pick"] == {"set:803": {"ids": [7]}} and st2["pending"] is None
    assert st2["asked"] is None and st2["utterances"] == ["u", "공학관 803"]

    st["pending"] = {"kind": "room", "key": "set:8층", "section": "set", "expr": "8층",
                     "options": ["bld:3"]}
    assert D.choose(st, "bld:3", "공학관")["room_pick"] == {"set:8층": {"building": 3}}

    st["pending"] = {"kind": "pick", "options": ["pick:7:r17", "pick:7:r18"]}
    assert D.choose(st, "pick:7:r18", "x")["pick"] == {"7": "r18"}

    st["pending"] = {"kind": "type", "section": "set",
                     "options": [c["id"] for c in D.TYPE_CHOICES]}
    assert D.choose(st, "type:특강", "특강")["set"]["type"] == "특강"
```

Run: `uv run pytest tests/test_assistant_dialog.py -q`
Expected: FAIL — `ImportError: cannot import name 'dialog'`.

- [ ] **Step 2: 구현**

`server/app/assistant/dialog.py`:
```python
"""대화 상태와 한 턴의 진행 (spec §4). 상태는 JSON 으로 DB(assistant_conversations.state)에 둔다 —
프로세스 메모리에 두지 않는다(워커 1개라도 재시작에 안전).

상태 키: intent · target · set(표현 그대로) · room_pick · pick · asked · pending · utterances"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from assistant_proto import TYPE_LABELS, Form, form_to_dict, rules

TYPE_CHOICES = [{"id": f"type:{x}", "label": x} for x in ("특강", "대여", "휴강", "수업", "시험")]


class Unsupported(Exception):
    """unknown — AI 비서가 할 수 없는 요청."""


class NeedContext(Exception):
    """이어 갈 대화가 없는데 fill·선택이 왔다(또는 내놓지 않은 선택지)."""


@dataclass
class Ask:
    question: str
    state: dict
    choices: list[dict] = field(default_factory=list)


@dataclass
class Fail:
    message: str
    state: dict


@dataclass
class Ready:
    draft: dict
    state: dict


@dataclass
class Answer:
    draft: dict


def new_state(form_dict: dict, utterance: str) -> dict:
    return {
        "intent": form_dict["intent"],
        "target": dict(form_dict["target"]),
        "set": dict(form_dict["set"]),
        "room_pick": {},
        "pick": {},
        "asked": None,
        "pending": None,
        "utterances": [utterance],
    }


def _merge(dst: dict, src: dict) -> None:
    """rooms 는 더하고(순서 유지·중복 제거), 나머지 칸은 덮어쓴다."""
    for k, v in src.items():
        dst[k] = list(dict.fromkeys([*dst.get("rooms", []), *v])) if k == "rooms" else v


def absorb(state: dict | None, form: Form, utterance: str) -> tuple[dict | None, str]:
    d = form_to_dict(form)
    if form.intent == "cancel":
        return None, "취소했습니다."
    if form.intent == "unknown":
        raise Unsupported
    if form.intent == "fill":
        if state is None:
            raise NeedContext
        st = copy.deepcopy(state)
        p = st.get("pending")
        if p and p["kind"] == "room" and "rooms" in d["set"]:  # 버튼 대신 말로 고른 강의실
            sec = p["section"]
            st[sec]["rooms"] = [x for x in st[sec].get("rooms", []) if x != p["expr"]]
        sec = (st["asked"] or f"{rules.PRIMARY[st['intent']]}.any").split(".")[0]
        _merge(st[sec], d["set"])
        _merge(st["target"], d["target"])
        st["utterances"].append(utterance)
        st["asked"], st["pending"], st["pick"] = None, None, {}
        return st, ""
    lead = "앞의 요청은 그만두고 새로 시작합니다. " if state is not None else ""
    return new_state(d, utterance), lead


def choose(state: dict | None, choice: str, utterance: str) -> dict:
    p = (state or {}).get("pending")
    if not p or choice not in p["options"]:
        raise NeedContext
    st = copy.deepcopy(state)
    kind, _, val = choice.partition(":")
    if kind == "room":
        st["room_pick"][p["key"]] = {"ids": [int(val)]}
    elif kind == "bld":
        st["room_pick"][p["key"]] = {"building": int(val)}
    elif kind == "pick":
        room_id, _, key = val.partition(":")
        st["pick"][room_id] = key
    elif kind == "type" and val in TYPE_LABELS:
        st[p["section"]]["type"] = val
    else:
        raise NeedContext
    st["utterances"].append(utterance)
    st["asked"], st["pending"] = None, None
    return st
```

- [ ] **Step 3: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_dialog.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

```bash
git add server/app/assistant/dialog.py server/tests/test_assistant_dialog.py
git commit -m "feat(server): AI 비서 대화 상태 — 반영·이어지는 답·선택지 고르기"
```

---

### Task 10: 한 턴 진행 — 해석 · 되묻기 · 대상 찾기 (`advance`)

**Files:**
- Create: `server/app/assistant/changes.py` (1부 — 대상 찾기·휴강 펼치기)
- Modify: `server/app/assistant/dialog.py` (import 교체 + 끝에 `advance` 추가)
- Test: `server/tests/test_assistant_advance.py`

**Interfaces:**
- Consumes: Task 8 `rooms.*`, Task 9 상태·결과 타입, `assistant_proto.resolve_*`·`type_code`·`rules.missing`·`rules.question`
- Produces:
  - `dialog.advance(s, sc, state, now_local) -> Ask | Fail | Ready | Answer`, 상수 `dialog.WEEKLY_HINT`, `dialog.EVENT_SPAN_MAX = 31`
  - **초안(draft)** = `{"intent", "target": R, "set": R, "pick": {..}, "utterances": [..]}`, `R` 의 키:
    `rooms: [room_id]` · `dates: ["YYYY-MM-DD"]` · `range: [시작, 끝]` · `weekdays: [1..7]` · `time: ["HH:MM", "HH:MM" | None]` · `type: 1..6` · `subject` · `professor` · `reason` · `requester` · (휴강) `entries: [{"room_id","date","start","end","subject","professor"}]`
  - `changes.d_(iso)`, `changes.hm("HH:MM")`, `changes.md(date) -> "11/27(금)"`, `changes.span(sh, sm, eh, em) -> "15:00–18:00"`, `changes.week_of(date) -> 월요일 iso`, `changes.TYPE`(코드→라벨), `changes.WD`
  - `changes.room_labels(s, ids) -> {room_id: "공학관 803"}`
  - `changes.fill_from_slots(s, draft) -> tuple[str, str] | None` — 휴강을 그날 정규 수업으로 펼쳐 `set.entries` 에 넣는다. 못 하면 `(묻는 칸, 문구)`
  - `changes.find_candidates(s, sc, draft, now_local) -> dict[int, list[dict]]` — 방별 후보. 후보 `key`: `r{id}`(예약)·`d{day}-{HHMM}`(정규)·`e{id}`(시험)·`q{id}`(신청, 방 키 `0` 하나에 모음)
  - `changes.chosen(cands, picks) -> dict[int, dict]`, `changes.not_found_message(intent) -> str`

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_advance.py`:
```python
import datetime as dt

from app.assistant import dialog as D
from tests.assistant_util import ALL, NOW, campus, resv

SPECIAL = {"rooms": ["803"], "when": "이번주 금요일", "time": "15시부터 18시까지", "type": "특강"}


def st(intent, target=None, set_=None):
    return D.new_state({"intent": intent, "target": target or {}, "set": set_ or {}}, "u")


def adv(app, state):
    with app.state.Session() as s:
        return D.advance(s, ALL, state, NOW)


def test_asks_missing_subject_first(app, school):
    campus(app)
    d = adv(app, st("event.add", set_=SPECIAL))
    assert isinstance(d, D.Ask) and d.question == "특강 이름은 무엇인가요?"
    assert d.state["asked"] == "set.subject" and d.choices == []


def test_type_question_offers_choices(app, school):
    campus(app)
    d = adv(app, st("event.add", set_={"rooms": ["803"], "when": "금요일"}))
    assert d.state["asked"] == "set.type" and d.choices[0] == {"id": "type:특강", "label": "특강"}
    assert d.state["pending"]["kind"] == "type"


def test_room_ambiguity_then_ready(app, school):
    ids = campus(app)
    d = adv(app, st("event.add", set_={**SPECIAL, "subject": "알고리즘 특강"}))
    assert isinstance(d, D.Ask)
    assert d.choices == [
        {"id": f"room:{ids['E803']}", "label": "공학관 803"},
        {"id": f"room:{ids['H803']}", "label": "인문관 803"},
    ]
    d2 = adv(app, D.choose(d.state, f"room:{ids['E803']}", "공학관 803"))
    assert isinstance(d2, D.Ready)
    assert d2.draft["set"] == {
        "rooms": [ids["E803"]],
        "dates": ["2026-11-27"],
        "time": ["15:00", "18:00"],
        "type": 5,
        "subject": "알고리즘 특강",
    }
    assert d2.draft["utterances"] == ["u", "공학관 803"]


def test_missing_room_reasks_and_drops_expr(app, school):
    campus(app)
    d = adv(app, st("event.add", set_={**SPECIAL, "rooms": ["999"], "subject": "x"}))
    assert isinstance(d, D.Ask) and d.question.startswith("'999' 강의실을 찾지 못했습니다")
    assert "rooms" not in d.state["set"] and d.state["asked"] == "set.rooms"


def test_bad_time_weekly_event_and_open_end(app, school):
    campus(app)
    base = {**SPECIAL, "rooms": ["공학관 803"], "subject": "x"}
    d = adv(app, st("event.add", set_={**base, "time": "몇 시"}))
    assert d.question == "시각을 '15시~18시'처럼 알려 주세요." and "time" not in d.state["set"]
    d = adv(app, st("event.add", set_={**base, "when": "매주 월"}))
    assert d.question == D.WEEKLY_HINT
    d = adv(app, st("event.add", set_={**base, "time": "15시"}))
    assert d.question.startswith("끝나는 시각도")


def test_holiday_fills_from_regular_class(app, school):
    ids = campus(app)
    d = adv(
        app,
        st("event.add", set_={"rooms": ["공학관 803"], "when": "다음 주 월요일", "type": "휴강",
                              "subject": "알고리즘"}),
    )
    assert isinstance(d, D.Ready)
    assert d.draft["set"]["entries"] == [
        {"room_id": ids["E803"], "date": "2026-11-30", "start": "09:00", "end": "12:00",
         "subject": "알고리즘", "professor": "이"}
    ]


def test_whole_day_holiday_takes_every_class(app, school):
    campus(app)
    d = adv(app, st("event.add", set_={"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "휴강"}))
    assert [e["subject"] for e in d.draft["set"]["entries"]] == ["자료구조"]
    d = adv(app, st("event.add", set_={"rooms": ["공학관 801"], "when": "이번주 금요일", "type": "휴강"}))
    assert isinstance(d, D.Ask) and d.state["asked"] == "set.time"  # 801 은 그날 수업이 없다


def test_change_with_two_candidates_asks_pick(app, school):
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 27), (17, 0), (18, 0), id_=17)
    resv(app, ids["E803"], dt.date(2026, 11, 27), (19, 0), (20, 0), id_=18)
    state = st(
        "event.change",
        target={"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "특강"},
        set_={"time": "16시"},
    )
    d = adv(app, state)
    assert isinstance(d, D.Ask)
    assert [c["id"] for c in d.choices] == [f"pick:{ids['E803']}:r17", f"pick:{ids['E803']}:r18"]
    assert d.choices[0]["label"] == "공학관 803 · 11/27(금) 17:00–18:00 특강 특강"
    d2 = adv(app, D.choose(d.state, f"pick:{ids['E803']}:r18", "19시 것"))
    assert isinstance(d2, D.Ready) and d2.draft["pick"] == {str(ids["E803"]): "r18"}


def test_change_not_found_fails(app, school):
    campus(app)
    d = adv(app, st("event.remove", target={"rooms": ["공학관 803"], "when": "이번주 금요일", "type": "특강"}))
    assert isinstance(d, D.Fail) and d.message.startswith("말씀하신 일정을 찾지 못했습니다")


def test_ask_answer_and_request_lists(app, school, students):
    ids = campus(app)
    d = adv(app, st("ask.node", target={"rooms": ["공학관 803"]}))
    assert isinstance(d, D.Answer) and d.draft["target"]["rooms"] == [ids["E803"]]
    for id_, room, who in ((31, "E801", "s1@mju.ac.kr"), (32, "E802", "s2@mju.ac.kr")):
        resv(app, ids[room], dt.date(2026, 11, 26), (13, 0), (14, 0), id_=id_, type_=6,
             subject="스터디", status="requested", requested_by=who)
    d = adv(app, st("request.approve"))
    assert isinstance(d, D.Ask) and [c["id"] for c in d.choices] == ["pick:0:q31", "pick:0:q32"]
    assert d.choices[0]["label"] == '공학관 801 11/26(목) 13:00–14:00 학생1 "스터디"'
    d = adv(app, st("request.approve", target={"requester": "학생1"}))
    assert isinstance(d, D.Ready)
```

Run: `uv run pytest tests/test_assistant_advance.py -q`
Expected: FAIL — `AttributeError: module 'app.assistant.dialog' has no attribute 'advance'`.

- [ ] **Step 2: `changes.py` 1부**

`server/app/assistant/changes.py`:
```python
"""초안(draft) → 대상 찾기 · 확정 변경 목록 · 요약 · 경고 (spec §5). DB 는 읽기만 — 쓰기는 preview.run_ops.

초안 = dialog.advance 가 만든 해석 결과 {"intent", "target": R, "set": R, "pick", "utterances"}.
R 의 키는 plan 01 Task 10 Interfaces 표 그대로."""

from __future__ import annotations

import datetime as dt

from assistant_proto import TYPE_LABELS
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import scope
from app.auth.models import User
from app.auth.scope import Scope
from app.domain import clock, reserve
from app.domain.models import Building, ExamPeriod, Reservation, Room, Slot

WD = "월화수목금토일"
TYPE = dict(enumerate(TYPE_LABELS, start=1))


def d_(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


def hm(x: str) -> tuple[int, int]:
    h, m = x.split(":")
    return int(h), int(m)


def md(d: dt.date) -> str:
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def span(sh: int, sm: int, eh: int, em: int) -> str:
    return f"{sh:02d}:{sm:02d}–{eh:02d}:{em:02d}"


def week_of(d: dt.date) -> str:
    return clock.week_start(d).isoformat()


def room_labels(s: Session, ids) -> dict[int, str]:
    q = (
        select(Room.id, Building.name, Room.room)
        .join(Building, Room.building_id == Building.id)
        .where(Room.id.in_(list(ids)))
    )
    return {rid: f"{name} {num}" for rid, name, num in s.execute(q).all()}


def _hit(x, s_min: int, e_min: int) -> bool:
    return x.s_h * 60 + x.s_m < e_min and s_min < x.e_h * 60 + x.e_m


def _match(x, tg: dict) -> bool:
    """시작 시각·유형·이름(서로 포함)이 맞는가 — 대상 찾기 공용."""
    if "time" in tg and (x.s_h, x.s_m) != hm(tg["time"][0]):
        return False
    if "type" in tg and x.type != tg["type"]:
        return False
    if "subject" in tg:
        want = tg["subject"]
        if not (x.subject and (want in x.subject or x.subject in want)):
            return False
    return True


def fill_from_slots(s: Session, draft: dict) -> tuple[str, str] | None:
    """휴강 — 그날 정규 수업에서 시각·이름을 찾아 set.entries 로 펼친다 (수업마다 휴강 하나).
    시각을 다 말했는데 그 시각 수업이 없으면 말한 시각 그대로. 아무것도 못 찾으면 (묻는 칸, 문구)."""
    st = draft["set"]
    if st.get("type") != 3:
        return None
    t = st.get("time")
    entries: list[dict] = []
    for rid in st["rooms"]:
        for iso in st["dates"]:
            day = d_(iso).isoweekday()
            q = (
                select(Slot)
                .where(Slot.room_id == rid, Slot.day == day, Slot.type != 4)
                .order_by(Slot.s_h, Slot.s_m)
            )
            for x in s.scalars(q):
                if t is not None:
                    sh, sm = hm(t[0])
                    if t[1] is None:
                        hit = (x.s_h, x.s_m) == (sh, sm)
                    else:
                        eh, em = hm(t[1])
                        hit = _hit(x, sh * 60 + sm, eh * 60 + em)
                elif "subject" in st:
                    hit = st["subject"] in x.subject
                else:
                    hit = True
                if hit:
                    entries.append(
                        {
                            "room_id": rid,
                            "date": iso,
                            "start": f"{x.s_h:02d}:{x.s_m:02d}",
                            "end": f"{x.e_h:02d}:{x.e_m:02d}",
                            "subject": x.subject,
                            "professor": x.professor,
                        }
                    )
    if not entries and t is not None and t[1] is not None:
        entries = [
            {
                "room_id": rid,
                "date": iso,
                "start": t[0],
                "end": t[1],
                "subject": st.get("subject", "휴강"),
                "professor": st.get("professor", ""),
            }
            for rid in st["rooms"]
            for iso in st["dates"]
        ]
    if not entries:
        return ("time", "그날 휴강할 정규 수업을 찾지 못했습니다. 몇 시부터 몇 시까지인지 알려 주세요.")
    st["entries"] = entries
    return None


def _event_cands(s: Session, rid: int, tg: dict) -> list[dict]:
    q = (
        select(Reservation)
        .where(
            Reservation.room_id == rid,
            Reservation.status == "approved",
            Reservation.date.in_([d_(x) for x in tg["dates"]]),
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id)
    )
    return [
        {
            "key": f"r{r.id}",
            "id": r.id,
            "date": r.date.isoformat(),
            "label": f"{md(r.date)} {span(r.s_h, r.s_m, r.e_h, r.e_m)} {TYPE[r.type]} {r.subject}".rstrip(),
        }
        for r in s.scalars(q)
        if _match(r, tg)
    ]


def _class_cands(s: Session, rid: int, tg: dict) -> list[dict]:
    q = (
        select(Slot)
        .where(Slot.room_id == rid, Slot.day.in_(tg["weekdays"]))
        .order_by(Slot.day, Slot.s_h, Slot.s_m)
    )
    return [
        {
            "key": f"d{x.day}-{x.s_h:02d}{x.s_m:02d}",
            "day": x.day,
            "s_h": x.s_h,
            "s_m": x.s_m,
            "label": f"{WD[x.day - 1]} {span(x.s_h, x.s_m, x.e_h, x.e_m)} {x.subject}",
        }
        for x in s.scalars(q)
        if _match(x, tg)
    ]


def _exam_cands(s: Session, rid: int, tg: dict) -> list[dict]:
    q = select(ExamPeriod).where(ExamPeriod.room_id == rid).order_by(ExamPeriod.date_start)
    if "range" in tg:
        a, z = d_(tg["range"][0]), d_(tg["range"][1])
        q = q.where(ExamPeriod.date_start <= z, ExamPeriod.date_end >= a)
    return [
        {
            "key": f"e{x.id}",
            "id": x.id,
            "start": x.date_start.isoformat(),
            "end": x.date_end.isoformat(),
            "label": f"{md(x.date_start)}~{md(x.date_end)}",
        }
        for x in s.scalars(q)
    ]


def _who(u: User | None, expr: str) -> bool:
    return u is not None and (
        expr in u.name or expr == (u.student_no or "") or expr == u.email.split("@")[0]
    )


def _request_cands(s: Session, sc: Scope, tg: dict, now_local: dt.datetime) -> list[dict]:
    q = (
        select(Reservation, Room, Building)
        .join(Room, Room.id == Reservation.room_id)
        .join(Building, Building.id == Room.building_id)
        .where(
            scope.building_clause(sc),
            Reservation.status == "requested",
            reserve.not_started(now_local),  # 시작 지난 신청은 승인 불가(409) — 목록에서도 뺀다
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id)
    )
    if "rooms" in tg:
        q = q.where(Room.id.in_(tg["rooms"]))
    if "dates" in tg:
        q = q.where(Reservation.date.in_([d_(x) for x in tg["dates"]]))
    out = []
    for r, room, b in s.execute(q).all():
        if not _match(r, {k: v for k, v in tg.items() if k in ("time", "type")}):
            continue
        u = s.get(User, r.requested_by) if r.requested_by else None
        if "requester" in tg and not _who(u, tg["requester"]):
            continue
        who = u.name if u else "-"
        out.append(
            {
                "key": f"q{r.id}",
                "id": r.id,
                "room_id": room.id,
                "date": r.date.isoformat(),
                "label": f'{b.name} {room.room} {md(r.date)} {span(r.s_h, r.s_m, r.e_h, r.e_m)} {who} "{r.subject}"',
            }
        )
    return out


def find_candidates(s: Session, sc: Scope, draft: dict, now_local: dt.datetime) -> dict[int, list[dict]]:
    """수정·삭제·승인 대상 후보 — 방별. 신청(request.*)은 방을 가로질러 방 키 0 하나에 모은다."""
    grp, tg = draft["intent"].split(".")[0], draft["target"]
    if grp == "request":
        return {0: _request_cands(s, sc, tg, now_local)}
    fn = {"event": _event_cands, "class": _class_cands, "exam": _exam_cands}[grp]
    return {rid: fn(s, rid, tg) for rid in tg["rooms"]}


def chosen(cands: dict[int, list[dict]], picks: dict[str, str]) -> dict[int, dict]:
    """방마다 대상 하나 — 후보가 하나면 그것, 여럿이면 고른 것. 0개인 방은 빠진다."""
    out = {}
    for rid, lst in cands.items():
        if len(lst) == 1:
            out[rid] = lst[0]
        elif len(lst) > 1:
            hit = [c for c in lst if c["key"] == picks.get(str(rid))]
            if hit:
                out[rid] = hit[0]
    return out


def not_found_message(intent: str) -> str:
    return {
        "event": "말씀하신 일정을 찾지 못했습니다. 날짜·시각·이름을 다시 알려 주세요.",
        "class": "말씀하신 정규 수업을 찾지 못했습니다. 요일·시각·과목을 다시 알려 주세요.",
        "exam": "시험기간을 찾지 못했습니다.",
        "request": "대기 중인 신청을 찾지 못했습니다.",
    }[intent.split(".")[0]]
```

- [ ] **Step 3: `dialog.advance`**

`server/app/assistant/dialog.py` 의 import 부분을 다음으로 바꾼다:
```python
from __future__ import annotations

import copy
import datetime as dt
from dataclasses import dataclass, field

from assistant_proto import (
    TYPE_LABELS,
    Form,
    form_to_dict,
    resolve_time,
    resolve_weekdays,
    resolve_when,
    rules,
    type_code,
)
from sqlalchemy.orm import Session

from app.assistant import changes, rooms
from app.auth.scope import Scope
```

그리고 파일 끝에 붙인다:
```python
EVENT_SPAN_MAX = 31  # 날짜 기간을 하루씩 펼칠 때 최대 일수
WEEKLY_HINT = "매주 반복되는 일정은 정규 시간표로 요청해 주세요. (예: 803 매주 월 9~12시 자료구조 추가)"


def _ask(state: dict, slot: str, question: str, *, choices=None, pending=None) -> Ask:
    st = copy.deepcopy(state)
    st["asked"], st["pending"] = slot, pending
    return Ask(question, st, choices or [])


def _reask(state: dict, sec: str, f: str, message: str) -> Ask:
    """풀지 못한 칸을 비우고 다시 묻는다 — 다음 답(fill)이 그 칸을 새로 채운다."""
    st = copy.deepcopy(state)
    st[sec].pop(f, None)
    return _ask(st, f"{sec}.{f}", message)


def _rooms(s: Session, sc: Scope, state: dict, sec: str, expr: str) -> list[int] | Ask:
    key = f"{sec}:{expr}"
    pick = state["room_pick"].get(key) or {}
    if "ids" in pick:
        ok = {r.id for r in rooms.scoped_rooms(s, sc)}
        if all(i in ok for i in pick["ids"]):  # 그사이 범위가 줄었으면 다시 푼다
            return pick["ids"]
    got = rooms.resolve_room_expr(s, sc, expr, only_building=pick.get("building"))
    if isinstance(got, rooms.Found):
        return [r.id for r in got.rooms]
    if isinstance(got, rooms.Ambiguous):
        opts = [{"id": i, "label": label} for i, label in got.options]
        return _ask(
            state,
            f"{sec}.rooms",
            f"'{expr}' 강의실이 여러 곳에 있습니다. 어느 곳인가요?",
            choices=opts,
            pending={
                "kind": "room",
                "key": key,
                "section": sec,
                "expr": expr,
                "options": [o["id"] for o in opts],
            },
        )
    st = copy.deepcopy(state)
    st[sec]["rooms"] = [x for x in st[sec]["rooms"] if x != expr]
    if not st[sec]["rooms"]:
        del st[sec]["rooms"]
    return _ask(
        st, f"{sec}.rooms", f"'{expr}' 강의실을 찾지 못했습니다. 강의실을 다시 알려 주세요. (예: 803, 공학관 803)"
    )


def _when(intent: str, sec: str, expr: str, now_local: dt.datetime) -> dict | str:
    """날짜 표현 → 초안 칸. 문자열을 돌려주면 그 문구로 다시 묻는다."""
    grp = intent.split(".")[0]
    if grp == "class":
        wds = resolve_weekdays(expr)
        if not wds:
            return "요일을 '월', '화목'처럼 알려 주세요."
        if intent == "class.change" and sec == "set" and len(wds) != 1:
            return "옮길 요일을 하나만 알려 주세요."
        return {"weekdays": list(wds)}
    w = resolve_when(expr, now_local)
    if w is None:
        if grp == "exam":
            return "기간을 '12/15~12/19'처럼 알려 주세요."
        return "날짜를 '12/3'이나 '이번 주 금요일'처럼 알려 주세요."
    if w.kind == "weekdays":
        return WEEKLY_HINT
    if grp == "exam":
        if w.kind == "range":
            return {"range": [w.start.isoformat(), w.end.isoformat()]}
        if len(w.dates) == 1:
            return {"range": [w.dates[0].isoformat()] * 2}
        return "시험기간은 '12/15~12/19'처럼 이어진 기간으로 알려 주세요."
    if w.kind == "range":
        n = (w.end - w.start).days + 1
        if n > EVENT_SPAN_MAX:
            return f"기간은 {EVENT_SPAN_MAX}일까지 한 번에 다룰 수 있습니다."
        days = [w.start + dt.timedelta(days=i) for i in range(n)]
        out = {"dates": [d.isoformat() for d in days], "range": [w.start.isoformat(), w.end.isoformat()]}
    else:
        out = {"dates": [d.isoformat() for d in w.dates]}
    if intent == "event.change" and sec == "set" and len(out["dates"]) != 1:
        return "옮길 날짜를 하나만 알려 주세요."
    return out


def advance(s: Session, sc: Scope, state: dict, now_local: dt.datetime) -> Ask | Fail | Ready | Answer:
    """빈 칸 → 강의실 → 날짜·시각 → (휴강 펼치기) → 대상 찾기 순으로 막히는 곳에서 묻는다."""
    intent = state["intent"]
    slot = rules.missing(intent, state["target"], state["set"])
    if slot:
        sec, f = slot.split(".")
        q = rules.question(intent, slot, state["set"].get("type") or state["target"].get("type"))
        if f == "type":
            return _ask(
                state,
                slot,
                q,
                choices=TYPE_CHOICES,
                pending={"kind": "type", "section": sec, "options": [c["id"] for c in TYPE_CHOICES]},
            )
        return _ask(state, slot, q)
    res: dict = {"target": {}, "set": {}}
    for sec in ("target", "set"):
        for expr in list(state[sec].get("rooms", [])):
            got = _rooms(s, sc, state, sec, expr)
            if isinstance(got, Ask):
                return got
            res[sec]["rooms"] = list(dict.fromkeys([*res[sec].get("rooms", []), *got]))
    for sec in ("target", "set"):
        d = state[sec]
        if "when" in d:
            v = _when(intent, sec, d["when"], now_local)
            if isinstance(v, str):
                return _reask(state, sec, "when", v)
            res[sec].update(v)
        if "time" in d:
            ts = resolve_time(d["time"])
            if ts is None:
                return _reask(state, sec, "time", "시각을 '15시~18시'처럼 알려 주세요.")
            end = ts.end.strftime("%H:%M") if ts.end else None
            res[sec]["time"] = [ts.start.strftime("%H:%M"), end]
        if "type" in d:
            res[sec]["type"] = type_code(d["type"])
        for f in ("subject", "professor", "reason", "requester"):
            if f in d:
                res[sec][f] = d[f]
    draft = {
        "intent": intent,
        "target": res["target"],
        "set": res["set"],
        "pick": dict(state["pick"]),
        "utterances": list(state["utterances"]),
    }
    if intent.startswith("ask."):
        return Answer(draft)
    if intent == "event.add" and (need := changes.fill_from_slots(s, draft)):
        return _reask(state, "set", need[0], need[1])
    st = draft["set"]
    if intent in ("event.add", "class.add") and "entries" not in st and st["time"][1] is None:
        return _reask(state, "set", "time", "끝나는 시각도 알려 주세요. (예: 15시~18시)")
    if intent.endswith(".add"):
        return Ready(draft, state)
    cands = changes.find_candidates(s, sc, draft, now_local)
    if not any(cands.values()):
        return Fail(changes.not_found_message(intent), state)
    labels = changes.room_labels(s, [r for r in cands if r])
    for room_id, lst in cands.items():
        if len(lst) > 1 and draft["pick"].get(str(room_id)) not in {c["key"] for c in lst}:
            opts = [
                {
                    "id": f"pick:{room_id}:{c['key']}",
                    "label": f"{labels[room_id]} · {c['label']}" if room_id else c["label"],
                }
                for c in lst
            ]
            return _ask(
                state,
                "target.pick",
                "어느 것인가요?",
                choices=opts,
                pending={"kind": "pick", "options": [o["id"] for o in opts]},
            )
    return Ready(draft, state)
```

- [ ] **Step 4: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_advance.py tests/test_assistant_dialog.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (`ruff format` 이 긴 줄을 나누면 그대로 받아들인다).

```bash
git add server/app/assistant/changes.py server/app/assistant/dialog.py server/tests/test_assistant_advance.py
git commit -m "feat(server): AI 비서 한 턴 진행 — 해석·되묻기·휴강 펼치기·대상 찾기"
```

---

### Task 11: 확정 변경 목록 + 미리보기

**Files:**
- Modify: `server/app/assistant/changes.py` (2부 — import 추가 + `Built`·`plan` 추가)
- Create: `server/app/assistant/preview.py` (1부 — `run_ops`·`fingerprint`·`week_data`·`marks`·`make_preview`)
- Test: `server/tests/test_assistant_preview.py`

**Interfaces:**
- Consumes: Task 6 `app.domain.ops`, router 의 `_ID_LOCK`·`_free_id`·`_existing_same_room`, `reserve.approve`·`reject`, Task 10 `find_candidates`·`chosen`
- Produces:
  - `changes.Built(ops, weeks, labels, summary, warnings, notices, blockers)` + `.room_ids`
  - `changes.plan(s, sc, draft, now_local) -> Built`
  - 확정 변경(op) 모양: `{"op": "slot.put", "room_id", "slot": SlotIn dict}` · `{"op": "slot.del", "room_id", "day", "s_h", "s_m"}` · `{"op": "resv.put", "room_id", "id": int | None, "resv": ResvIn dict}` · `{"op": "resv.del", "room_id", "id"}` · `{"op": "exam.put", "room_id", "id": int | None, "exam": ExamIn dict}` · `{"op": "exam.del", "room_id", "id"}` · `{"op": "request.approve", "room_id", "id"}` · `{"op": "request.reject", "room_id", "id", "reason"}`
  - `preview.run_ops(s, sc, ops, actor_email, now_local) -> tuple[list[int], set[str]]` — (outbox id, 알릴 modem_id). 커밋하지 않는다. 범위 밖 방은 404.
  - `preview.fingerprint(s, room_ids) -> str`, `preview.week_data(s, room_id, week_start | None) -> dict`(부록 `WeekData`, JSON 모드), `preview.marks(before, after) -> list[dict]`
  - `preview.make_preview(Session, sc, conv_id, draft, now_local) -> dict` — 부록 `PreviewOut` 그대로. `assistant_previews` 에 행 저장(만료 10분)
  - `preview.PREVIEW_TTL = timedelta(minutes=10)`

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_preview.py`:
```python
import datetime as dt
import json

from sqlalchemy import func, select

from app.assistant import preview as P
from app.assistant.models import AssistantPreview
from app.domain.models import ExamPeriod, Reservation, Slot
from app.lora_service.models import Outbox
from tests.assistant_util import ALL, NOW, UTC_NOW, campus, fix_clock, resv


def _draft(intent, target=None, set_=None, pick=None):
    return {"intent": intent, "target": target or {}, "set": set_ or {}, "pick": pick or {},
            "utterances": ["u"]}


def _counts(app):
    with app.state.Session() as s:
        return tuple(
            s.scalar(select(func.count()).select_from(m))
            for m in (Slot, Reservation, ExamPeriod, Outbox)
        )


def _special(ids, date="2026-11-27", start="15:00", end="18:00"):
    return _draft("event.add", set_={"rooms": [ids["E803"]], "dates": [date],
                                     "time": [start, end], "type": 5, "subject": "알고리즘 특강"})


def test_event_add_preview_diff_and_no_residue(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    before = _counts(app)
    pv = P.make_preview(app.state.Session, ALL, "c_t", _special(ids), NOW)
    assert pv["blockers"] == []
    assert pv["summary"] == ['+ 11/27(금) 15:00–18:00 특강 "알고리즘 특강" (공학관 803)']
    assert any("자료구조" in w for w in pv["warnings"])
    [room] = pv["rooms"]
    assert (room["room_id"], room["label"], room["added"], room["removed"], room["changed"]) == (
        ids["E803"], "공학관 803", 1, 0, 0)
    [wk] = room["weeks"]
    assert wk["week_start"] == "2026-11-23" and wk["before"]["reservations"] == []
    assert [x["subject"] for x in wk["after"]["slots"]] == ["알고리즘", "자료구조"]
    [new] = wk["after"]["reservations"]
    assert (new["subject"], new["date"], new["type"]) == ("알고리즘 특강", "2026-11-27", 5)
    assert wk["changes"] == [{"entity": "resv", "key": f"r{new['id']}", "op": "add", "fields": []}]
    assert _counts(app) == before  # rollback — 도메인 행·outbox 아무것도 남지 않는다
    with app.state.Session() as s:
        p = s.get(AssistantPreview, pv["preview_id"])
        assert p.applied_at is None and json.loads(p.ops)[0]["op"] == "resv.put"
        assert p.expires_at - UTC_NOW == dt.timedelta(minutes=10)


def test_past_time_is_blocked(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = P.make_preview(app.state.Session, ALL, "c_t", _special(ids, "2026-11-25", "09:00", "10:00"), NOW)
    assert any("이미 지난 시각" in b for b in pv["blockers"])


def test_notice_outside_node_window(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = P.make_preview(app.state.Session, ALL, "c_t", _special(ids, "2026-12-10"), NOW)
    assert "12/10(목) 일정은 저장해 두고 12/3(목)부터 문 앞 화면에 보냅니다." in pv["notices"]


def test_op_error_becomes_blocker(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    with app.state.Session() as s, s.begin():
        s.add(Slot(room_id=ids["E801"], day=2, s_h=9, s_m=0, e_h=10, e_m=0, type=1,
                   subject="긴급", professor="", source=3))
    d = _draft("class.change", target={"rooms": [ids["E801"]], "weekdays": [2], "time": ["09:00", None]},
               set_={"subject": "새과목"})
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    assert any("source 3" in b for b in pv["blockers"])
    assert pv["rooms"][0]["weeks"][0]["changes"] == []  # 실패하면 바뀐 뒤 = 바뀌기 전


def test_class_change_moves_slot(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    d = _draft("class.change", target={"rooms": [ids["E803"]], "weekdays": [1], "subject": "알고리즘"},
               set_={"weekdays": [2]})
    pv = P.make_preview(app.state.Session, ALL, "c_t", d, NOW)
    [wk] = pv["rooms"][0]["weeks"]
    assert wk["week_start"] is None and wk["after"]["reservations"] == []
    assert [(m["key"], m["op"]) for m in wk["changes"]] == [("d1-0900", "remove"), ("d2-0900", "add")]
    assert pv["summary"][0].startswith("~ 매주 월 09:00–12:00 알고리즘 → 화 09:00–12:00")


def test_request_approve_marks_status_change(client, app, students, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    resv(app, ids["E801"], dt.date(2026, 11, 26), (13, 0), (14, 0), id_=31, type_=6,
         subject="스터디", status="requested", requested_by="s1@mju.ac.kr")
    pv = P.make_preview(app.state.Session, ALL, "c_t",
                        _draft("request.approve", target={"requester": "학생1"}), NOW)
    assert pv["summary"] == ['✓ 승인 공학관 801 11/26(목) 13:00–14:00 학생1 "스터디"']
    [wk] = pv["rooms"][0]["weeks"]
    assert wk["changes"] == [{"entity": "resv", "key": "r31", "op": "change", "fields": ["status"]}]


def test_fingerprint_tracks_only_given_rooms(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    with app.state.Session() as s:
        fp = P.fingerprint(s, [ids["E803"]])
    resv(app, ids["E801"], dt.date(2026, 11, 27), (9, 0), (10, 0), id_=40)
    with app.state.Session() as s:
        assert P.fingerprint(s, [ids["E803"]]) == fp
    resv(app, ids["E803"], dt.date(2026, 11, 27), (9, 0), (10, 0), id_=41)
    with app.state.Session() as s:
        assert P.fingerprint(s, [ids["E803"]]) != fp
```

Run: `uv run pytest tests/test_assistant_preview.py -q`
Expected: FAIL — `ImportError: cannot import name 'preview'`.

- [ ] **Step 2: `changes.py` 2부**

`server/app/assistant/changes.py` 맨 위 import 에 더한다:
```python
from dataclasses import dataclass, field
```
```python
from app.domain import admin, clock, reserve
from app.domain.topology import RESV_HORIZON_DAYS
```
(기존 `from app.domain import clock, reserve` 줄은 위 줄로 바꾼다.)

파일 끝에 붙인다:
```python
WEEKS_MAX = 3  # 한 방에 그리는 주 수 (시험기간이 길어도)


@dataclass
class Built:
    ops: list[dict] = field(default_factory=list)
    weeks: dict[int, list[str | None]] = field(default_factory=dict)  # 방 → 그릴 주(월요일 iso, None=정규)
    labels: dict[int, str] = field(default_factory=dict)
    summary: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def week(self, room_id: int, wk: str | None) -> None:
        lst = self.weeks.setdefault(room_id, [])
        if wk not in lst and len(lst) < WEEKS_MAX:
            lst.append(wk)

    @property
    def room_ids(self) -> list[int]:
        return sorted(self.weeks)


def _checks(s, b: Built, rid, d, s_min, e_min, exclude_id, type_, now_local) -> None:
    label = b.labels[rid]
    if clock.local_dt(d, s_min // 60, s_min % 60) <= now_local:
        b.blockers.append(f"{label} {md(d)} {s_min // 60:02d}:{s_min % 60:02d} 은 이미 지난 시각입니다.")
    if e_min <= s_min:
        b.blockers.append(f"{label} {md(d)}: 시작이 끝보다 늦습니다.")
    if type_ != 3:  # 휴강은 정규 수업과 겹치는 게 정상
        q = select(Slot).where(Slot.room_id == rid, Slot.day == d.isoweekday(), Slot.type != 4)
        for x in s.scalars(q):
            if _hit(x, s_min, e_min):
                b.warnings.append(
                    f'{label} 기존 수업 "{x.subject}"({WD[x.day - 1]} {span(x.s_h, x.s_m, x.e_h, x.e_m)})와 겹칩니다.'
                )
        q = select(Reservation).where(
            Reservation.room_id == rid,
            Reservation.date == d,
            Reservation.status.in_(("approved", "requested")),
        )
        if exclude_id is not None:
            q = q.where(Reservation.id != exclude_id)
        for r in s.scalars(q):
            if _hit(r, s_min, e_min):
                what = "대기 중인 학생 신청" if r.status == "requested" else "기존 일정"
                b.warnings.append(
                    f'{label} {what} "{r.subject}"({md(r.date)} {span(r.s_h, r.s_m, r.e_h, r.e_m)})와 겹칩니다.'
                )
    if d > now_local.date() + dt.timedelta(days=RESV_HORIZON_DAYS):
        b.notices.append(
            f"{md(d)} 일정은 저장해 두고 {md(d - dt.timedelta(days=RESV_HORIZON_DAYS))}부터 문 앞 화면에 보냅니다."
        )


def _new_span(old: tuple[int, int, int, int], st: dict) -> tuple[int, int, int, int] | None:
    """set.time 반영. 시작만 말했으면 원래 길이 유지. 자정을 넘으면 None."""
    if "time" not in st:
        return old
    sh, sm, eh, em = old
    nsh, nsm = hm(st["time"][0])
    if st["time"][1]:
        neh, nem = hm(st["time"][1])
    else:
        end = nsh * 60 + nsm + (eh * 60 + em) - (sh * 60 + sm)
        if end >= 24 * 60:
            return None
        neh, nem = divmod(end, 60)
    return nsh, nsm, neh, nem


def _resv_op(rid, id_, d, sp, type_, subj, prof) -> dict:
    sh, sm, eh, em = sp
    return {
        "op": "resv.put",
        "room_id": rid,
        "id": id_,
        "resv": {"date": d.isoformat(), "s_h": sh, "s_m": sm, "e_h": eh, "e_m": em,
                 "type": type_, "subject": subj, "professor": prof},
    }


def _event_add(s, b: Built, st: dict, now_local) -> None:
    if "entries" in st:  # 휴강 — 정규 수업마다 하나
        items = [
            (e["room_id"], d_(e["date"]), (*hm(e["start"]), *hm(e["end"])), e["subject"], e["professor"])
            for e in st["entries"]
        ]
    else:
        sp = (*hm(st["time"][0]), *hm(st["time"][1]))
        items = [
            (rid, d_(iso), sp, st.get("subject", ""), st.get("professor", ""))
            for rid in st["rooms"]
            for iso in st["dates"]
        ]
    for rid, d, sp, subj, prof in items:
        sh, sm, eh, em = sp
        b.ops.append(_resv_op(rid, None, d, sp, st["type"], subj, prof))
        b.week(rid, week_of(d))
        b.summary.append(f'+ {md(d)} {span(*sp)} {TYPE[st["type"]]} "{subj}" ({b.labels[rid]})')
        _checks(s, b, rid, d, sh * 60 + sm, eh * 60 + em, None, st["type"], now_local)


def _event_change(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        r = s.get(Reservation, c["id"])
        d = d_(st["dates"][0]) if "dates" in st else r.date
        sp = _new_span((r.s_h, r.s_m, r.e_h, r.e_m), st)
        if sp is None:
            b.blockers.append(f"{b.labels[rid]} {c['label']}: 끝 시각이 자정을 넘습니다.")
            continue
        type_ = st.get("type", r.type)
        subj, prof = st.get("subject", r.subject), st.get("professor", r.professor)
        b.ops.append(_resv_op(rid, r.id, d, sp, type_, subj, prof))
        b.week(rid, week_of(r.date))
        b.week(rid, week_of(d))
        b.summary.append(f'~ {c["label"]} → {md(d)} {span(*sp)} {TYPE[type_]} "{subj}" ({b.labels[rid]})')
        _checks(s, b, rid, d, sp[0] * 60 + sp[1], sp[2] * 60 + sp[3], r.id, type_, now_local)


def _event_remove(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        b.ops.append({"op": "resv.del", "room_id": rid, "id": c["id"]})
        b.week(rid, week_of(d_(c["date"])))
        b.summary.append(f"− {c['label']} ({b.labels[rid]})")


def _exam_weeks(b: Built, rid: int, a: dt.date, z: dt.date) -> None:
    mon = clock.week_start(a)
    while mon <= z:
        b.week(rid, mon.isoformat())
        mon += dt.timedelta(days=7)


def _exam_add(s, b: Built, st: dict, now_local) -> None:
    a, z = d_(st["range"][0]), d_(st["range"][1])
    if z < now_local.date():
        b.blockers.append(f"{md(a)}~{md(z)} 은 이미 지난 기간입니다.")
    for rid in st["rooms"]:
        b.ops.append({"op": "exam.put", "room_id": rid, "id": None,
                      "exam": {"date_start": a.isoformat(), "date_end": z.isoformat()}})
        _exam_weeks(b, rid, a, z)
        b.summary.append(f"+ 시험기간 {md(a)}~{md(z)} ({b.labels[rid]})")


def _exam_change(s, b: Built, ch: dict, st: dict, now_local) -> None:
    a, z = d_(st["range"][0]), d_(st["range"][1])
    for rid, c in ch.items():
        b.ops.append({"op": "exam.put", "room_id": rid, "id": c["id"],
                      "exam": {"date_start": a.isoformat(), "date_end": z.isoformat()}})
        _exam_weeks(b, rid, d_(c["start"]), d_(c["end"]))
        _exam_weeks(b, rid, a, z)
        b.summary.append(f"~ 시험기간 {c['label']} → {md(a)}~{md(z)} ({b.labels[rid]})")


def _exam_remove(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        b.ops.append({"op": "exam.del", "room_id": rid, "id": c["id"]})
        _exam_weeks(b, rid, d_(c["start"]), d_(c["end"]))
        b.summary.append(f"− 시험기간 {c['label']} ({b.labels[rid]})")


def _class_add(s, b: Built, st: dict, now_local) -> None:
    sh, sm, eh, em = (*hm(st["time"][0]), *hm(st["time"][1]))
    type_ = st.get("type", 1)
    if eh * 60 + em <= sh * 60 + sm:
        b.blockers.append("시작이 끝보다 늦습니다.")
    for rid in st["rooms"]:
        for wd in st["weekdays"]:
            b.ops.append({"op": "slot.put", "room_id": rid, "slot": {
                "day": wd, "s_h": sh, "s_m": sm, "e_h": eh, "e_m": em, "type": type_,
                "subject": st["subject"], "professor": st.get("professor", ""), "source": 2}})
            b.week(rid, None)
            b.summary.append(
                f'+ 매주 {WD[wd - 1]} {span(sh, sm, eh, em)} {TYPE[type_]} "{st["subject"]}" ({b.labels[rid]})'
            )
            for x in s.scalars(select(Slot).where(Slot.room_id == rid, Slot.day == wd)):
                if (x.s_h, x.s_m) != (sh, sm) and _hit(x, sh * 60 + sm, eh * 60 + em):
                    b.warnings.append(
                        f'{b.labels[rid]} 기존 수업 "{x.subject}"({WD[wd - 1]} {span(x.s_h, x.s_m, x.e_h, x.e_m)})와 겹칩니다.'
                    )


def _class_change(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        x = s.scalar(select(Slot).where(Slot.room_id == rid, Slot.day == c["day"],
                                        Slot.s_h == c["s_h"], Slot.s_m == c["s_m"]))
        day = st["weekdays"][0] if "weekdays" in st else x.day
        sp = _new_span((x.s_h, x.s_m, x.e_h, x.e_m), st)
        if sp is None:
            b.blockers.append(f"{b.labels[rid]} {c['label']}: 끝 시각이 자정을 넘습니다.")
            continue
        sh, sm, eh, em = sp
        new = {"day": day, "s_h": sh, "s_m": sm, "e_h": eh, "e_m": em,
               "type": st.get("type", x.type), "subject": st.get("subject", x.subject),
               "professor": st.get("professor", x.professor), "source": 2}
        if (day, sh, sm) != (x.day, x.s_h, x.s_m):
            b.ops.append({"op": "slot.del", "room_id": rid, "day": x.day, "s_h": x.s_h, "s_m": x.s_m})
        b.ops.append({"op": "slot.put", "room_id": rid, "slot": new})
        b.week(rid, None)
        b.summary.append(
            f'~ 매주 {c["label"]} → {WD[day - 1]} {span(*sp)} {new["subject"]} {new["professor"]} ({b.labels[rid]})'.rstrip()
        )


def _class_remove(s, b: Built, ch: dict, st: dict, now_local) -> None:
    for rid, c in ch.items():
        b.ops.append({"op": "slot.del", "room_id": rid, "day": c["day"], "s_h": c["s_h"], "s_m": c["s_m"]})
        b.week(rid, None)
        b.summary.append(f"− 매주 {c['label']} ({b.labels[rid]})")


def _request(b: Built, ch: dict, st: dict, approve: bool) -> None:
    for c in ch.values():
        rid = c["room_id"]
        if approve:
            b.ops.append({"op": "request.approve", "room_id": rid, "id": c["id"]})
            b.summary.append(f"✓ 승인 {c['label']}")
        else:
            reason = st.get("reason", "관리자 거절")
            b.ops.append({"op": "request.reject", "room_id": rid, "id": c["id"], "reason": reason})
            b.summary.append(f"✗ 거절 {c['label']} — {reason}")
        b.week(rid, week_of(d_(c["date"])))


_BUILD = {
    "event.change": _event_change,
    "event.remove": _event_remove,
    "exam.change": _exam_change,
    "exam.remove": _exam_remove,
    "class.change": _class_change,
    "class.remove": _class_remove,
}


def plan(s: Session, sc: Scope, draft: dict, now_local: dt.datetime) -> Built:
    it, tg, st = draft["intent"], draft["target"], draft["set"]
    b = Built()
    cands: dict[int, list[dict]] = {}
    ch: dict[int, dict] = {}
    if not it.endswith(".add"):
        cands = find_candidates(s, sc, draft, now_local)
        ch = chosen(cands, draft["pick"])
    ids = set(st.get("rooms", [])) | set(tg.get("rooms", []))
    ids |= {c["room_id"] for c in ch.values() if "room_id" in c}
    b.labels = room_labels(s, ids)
    for rid, lst in cands.items():
        if rid and not lst:
            b.notices.append(f"{b.labels[rid]}: 해당 항목이 없어 건너뜁니다.")
    if it == "event.add":
        _event_add(s, b, st, now_local)
    elif it == "exam.add":
        _exam_add(s, b, st, now_local)
    elif it == "class.add":
        _class_add(s, b, st, now_local)
    elif it in ("request.approve", "request.reject"):
        _request(b, ch, st, it == "request.approve")
    else:
        _BUILD[it](s, b, ch, st, now_local)
    rooms_now = set(b.room_ids)
    for n in admin.expected_nodes(s, sc):
        if n["room_id"] in rooms_now and "unseen" in n["warnings"]:
            b.warnings.append(f"{b.labels[n['room_id']]} 노드가 응답하지 않습니다 — 연결되면 전송됩니다.")
    b.warnings = list(dict.fromkeys(b.warnings))
    b.notices = list(dict.fromkeys(b.notices))
    b.blockers = list(dict.fromkeys(b.blockers))
    return b
```

- [ ] **Step 3: `preview.py` 1부**

`server/app/assistant/preview.py`:
```python
"""미리보기·적용 (spec §5.2·§5.4). 둘 다 같은 run_ops(= app.domain.ops 의 쓰기 함수)를 _ID_LOCK 안에서 돌린다.
미리보기 = 실행 → 읽기 → rollback, 적용 = 저장된 확정 변경 목록 실행 → 커밋 → notify.
요청 세션(_DB)이 아니라 새 세션을 연다 — 쓰고 되돌리는 일을 요청 세션과 섞지 않는다."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets

import pydantic
import sqlalchemy.exc
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import schemas as S
from app.assistant import changes
from app.assistant.models import AssistantPreview
from app.auth import scope
from app.auth.scope import Scope
from app.domain import admin, clock, reserve
from app.domain import ops as dops
from app.domain import router as R
from app.domain.models import ExamPeriod, Reservation, Room, Slot
from app.lora_service import api

PREVIEW_TTL = dt.timedelta(minutes=10)
_OP_ERRORS = (
    HTTPException,
    api.ValidationError,
    api.NotFound,
    pydantic.ValidationError,
    sqlalchemy.exc.IntegrityError,
)
_SLOT_F = ("e_h", "e_m", "type", "subject", "professor")
_RESV_F = ("date", "s_h", "s_m", "e_h", "e_m", "type", "subject", "professor", "status")
_EXAM_F = ("date_start", "date_end")


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _message(e: Exception) -> str:
    if isinstance(e, HTTPException):
        return str(e.detail)
    if isinstance(e, pydantic.ValidationError):
        return f"입력값이 규칙에 맞지 않습니다: {e.errors()[0].get('msg', '')}"
    if isinstance(e, sqlalchemy.exc.IntegrityError):
        return "저장할 수 없는 변경입니다(제약 위반)."
    return str(e)


def run_ops(
    s: Session, sc: Scope, ops_: list[dict], actor: str, now_local: dt.datetime
) -> tuple[list[int], set[str]]:
    """확정 변경 목록 실행 — 커밋하지 않는다. 호출자가 _ID_LOCK 을 잡는다."""
    ids: list[int] = []
    modems: set[str] = set()
    for op in ops_:
        room = scope.get_scoped(s, Room, op["room_id"], sc)  # 범위 재확인 — 밖이면 404
        bld, num, mid = dops.room_addr(s, room.id)
        if mid:
            modems.add(mid)
        k = op["op"]
        if k == "slot.put":
            ids += dops.put_slot(s, room.id, bld, num, S.SlotIn(**op["slot"]))
        elif k == "slot.del":
            ids += dops.delete_slot(s, room.id, bld, num, op["day"], op["s_h"], op["s_m"])
        elif k == "resv.put":
            body = S.ResvIn(**op["resv"])
            if op["id"] is None:
                rid, obj = R._free_id(s, Reservation), None
            else:
                rid, obj = op["id"], R._existing_same_room(s, Reservation, op["id"], room.id)
            ids += dops.write_resv(s, room.id, body, rid, obj, now_local)
        elif k == "resv.del":
            ids += dops.delete_resv(s, room.id, op["id"], now_local) or []
        elif k == "exam.put":
            body = S.ExamIn(**op["exam"])
            if op["id"] is None:
                eid, obj = R._free_id(s, ExamPeriod), None
            else:
                eid, obj = op["id"], R._existing_same_room(s, ExamPeriod, op["id"], room.id)
            ids += dops.write_exam(s, room.id, bld, num, body, eid, obj)
        elif k == "exam.del":
            ids += dops.delete_exam(s, room.id, bld, num, op["id"])
        elif k in ("request.approve", "request.reject"):
            r = s.get(Reservation, op["id"])
            if r is None or r.room_id != room.id:
                raise HTTPException(409, "신청을 찾지 못했습니다 — 이미 처리됐을 수 있습니다")
            if k == "request.approve":
                ids += reserve.approve(s, r, actor, now_local)
            else:
                reserve.reject(s, r, actor, op["reason"], now_local)
        else:
            raise ValueError(f"모르는 op {k}")
        s.flush()  # 다음 채번·용량 검사가 방금 쓴 행을 보게
    return ids, modems


def fingerprint(s: Session, room_ids: list[int]) -> str:
    """미리보기 뒤 같은 방들이 바뀌었는지 — 정규 시간표·예약·시험기간 전부 (pushed_at 은 빼고)."""
    h = hashlib.sha256()
    for rid in sorted(room_ids):
        q = select(Slot).where(Slot.room_id == rid).order_by(Slot.day, Slot.s_h, Slot.s_m)
        for x in s.scalars(q):
            h.update(repr(("s", rid, x.day, x.s_h, x.s_m, x.e_h, x.e_m, x.type, x.subject,
                           x.professor, x.source)).encode())
        q = select(Reservation).where(Reservation.room_id == rid).order_by(Reservation.id)
        for x in s.scalars(q):
            h.update(repr(("r", x.id, x.date.isoformat(), x.s_h, x.s_m, x.e_h, x.e_m, x.type,
                           x.subject, x.professor, x.status)).encode())
        q = select(ExamPeriod).where(ExamPeriod.room_id == rid).order_by(ExamPeriod.id)
        for x in s.scalars(q):
            h.update(repr(("e", x.id, x.date_start.isoformat(), x.date_end.isoformat())).encode())
    return h.hexdigest()


def week_data(s: Session, room_id: int, wk: str | None) -> dict:
    """부록 WeekData — 정규 시간표 전부 + (주가 있으면) 그 주 승인·신청 예약과 겹치는 시험기간. JSON 모드."""
    q = select(Slot).where(Slot.room_id == room_id).order_by(Slot.day, Slot.s_h, Slot.s_m)
    slots = [S.SlotWithRoom.model_validate(x).model_dump(mode="json") for x in s.scalars(q)]
    if wk is None:
        return {"slots": slots, "reservations": [], "exams": []}
    mon = dt.date.fromisoformat(wk)
    sun = mon + dt.timedelta(days=6)
    rows = admin.resv_with_room_rows(
        s,
        select(Reservation)
        .where(
            Reservation.room_id == room_id,
            Reservation.status.in_(("approved", "requested")),
            Reservation.date.between(mon, sun),
        )
        .order_by(Reservation.date, Reservation.s_h, Reservation.s_m, Reservation.id),
    )
    q = (
        select(ExamPeriod)
        .where(ExamPeriod.room_id == room_id, ExamPeriod.date_start <= sun, ExamPeriod.date_end >= mon)
        .order_by(ExamPeriod.date_start)
    )
    return {
        "slots": slots,
        "reservations": [S.ResvWithRoom.model_validate(x).model_dump(mode="json") for x in rows],
        "exams": [S.ExamWithRoom.model_validate(x).model_dump(mode="json") for x in s.scalars(q)],
    }


def _keyed(w: dict) -> dict[str, tuple[str, dict, tuple[str, ...]]]:
    out = {}
    for x in w["slots"]:
        out[f"d{x['day']}-{x['s_h']:02d}{x['s_m']:02d}"] = ("slot", x, _SLOT_F)
    for x in w["reservations"]:
        out[f"r{x['id']}"] = ("resv", x, _RESV_F)
    for x in w["exams"]:
        out[f"e{x['id']}"] = ("exam", x, _EXAM_F)
    return out


def marks(before: dict, after: dict) -> list[dict]:
    """부록 changes[] — key 규칙 d{day}-{HHMM} · r{id} · e{id}."""
    b, a = _keyed(before), _keyed(after)
    out = []
    for k in sorted(b.keys() | a.keys()):
        if k not in a:
            out.append({"entity": b[k][0], "key": k, "op": "remove", "fields": []})
        elif k not in b:
            out.append({"entity": a[k][0], "key": k, "op": "add", "fields": []})
        else:
            ent, x, fs = a[k]
            changed = [f for f in fs if x[f] != b[k][1][f]]
            if changed:
                out.append({"entity": ent, "key": k, "op": "change", "fields": changed})
    return out


def make_preview(
    Session: sessionmaker, sc: Scope, conv_id: str, draft: dict, now_local: dt.datetime
) -> dict:
    now_utc = clock.to_utc(now_local)
    with Session() as s:
        built = changes.plan(s, sc, draft, now_local)
    blockers = list(built.blockers)
    keys = [(rid, wk) for rid in built.room_ids for wk in built.weeks[rid]]
    with R._ID_LOCK, Session() as s:
        try:
            fp = fingerprint(s, built.room_ids)
            before = {k: week_data(s, *k) for k in keys}
            try:
                run_ops(s, sc, built.ops, sc.email, now_local)
                after = {k: week_data(s, *k) for k in keys}
            except _OP_ERRORS as e:
                blockers.append(_message(e))
                after = before
        finally:
            s.rollback()  # 미리보기는 아무것도 남기지 않는다 — 도메인 행·outbox·버전 모두
    with Session() as s:  # 적용 뒤 전송 추적이 건물 단위로 outbox 를 읽는다(03 웹)
        bld_of = dict(s.execute(select(Room.id, Room.building_id).where(Room.id.in_(built.room_ids))).all())
    rooms_out = []
    for rid in built.room_ids:
        weeks, seen = [], set()
        for wk in built.weeks[rid]:
            ms = marks(before[(rid, wk)], after[(rid, wk)])
            seen |= {(m["key"], m["op"]) for m in ms}
            weeks.append({"week_start": wk, "before": before[(rid, wk)], "after": after[(rid, wk)],
                          "changes": ms})
        rooms_out.append({
            "room_id": rid,
            "building_id": bld_of[rid],
            "label": built.labels[rid],
            "added": sum(op == "add" for _, op in seen),
            "removed": sum(op == "remove" for _, op in seen),
            "changed": sum(op == "change" for _, op in seen),
            "weeks": weeks,
        })
    pid = "p_" + secrets.token_hex(8)
    expires = now_utc + PREVIEW_TTL
    with Session() as s, s.begin():
        s.add(AssistantPreview(
            id=pid, conversation_id=conv_id, user_email=sc.email, draft=_j(draft),
            ops=_j(built.ops), room_ids=_j(built.room_ids), fingerprint=fp,
            blockers=_j(blockers), summary=_j(built.summary), created_at=now_utc,
            expires_at=expires,
        ))
    return {
        "preview_id": pid,
        "expires_at": expires.replace(tzinfo=dt.UTC),
        "summary": built.summary,
        "blockers": blockers,
        "warnings": built.warnings,
        "notices": built.notices,
        "rooms": rooms_out,
    }
```

- [ ] **Step 4: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_preview.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS. (`test_event_add_preview_diff_and_no_residue` 의 `_counts` 가 다르면 `run_ops` 안에서 커밋이 일어난 것 — `ops.py`·`reserve` 에 커밋이 없는지 본다.)

```bash
git add server/app/assistant/changes.py server/app/assistant/preview.py server/tests/test_assistant_preview.py
git commit -m "feat(server): AI 비서 미리보기 — 확정 변경 목록·전후 주간표·표시·막음/경고/안내, 실행 후 rollback"
```

---

### Task 12: 적용 · 변경 기록 · 모델 안내 파일

**Files:**
- Create: `server/app/assistant/manifest.py`, `server/app/assistant/model.json`
- Modify: `server/app/assistant/preview.py` (2부 — import 추가 + `apply_preview`)
- Test: `server/tests/test_assistant_apply.py`

**Interfaces:**
- Produces:
  - `manifest.MODEL_FILE`, `manifest.load(path=None) -> dict`(부록 §4.1, 형식이 틀리면 `ValueError`), `manifest.current_revision(path=None) -> str | None`
  - `preview.apply_preview(Session, sc, preview_id, now_local) -> tuple[int, dict]` — 200 `{"change_id", "outbox_ids"}` · 404 `{"detail": "미리보기 없음"}`(없음·다른 관리자) · 410 `{"detail": "expired"}` · 422 `{"detail": "blocked", "blockers"}` · 409 `{"detail": "stale", "preview": PreviewOut}`(옛 미리보기는 그 자리에서 만료)
  - 적용은 한 트랜잭션 — 하나라도 실패하면 아무것도 바뀌지 않고 422

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_apply.py`:
```python
import datetime as dt
import json

from fastapi import HTTPException
from sqlalchemy import func, select

from app.assistant import preview as P
from app.assistant.models import AssistantChange, AssistantPreview
from app.auth.scope import Scope
from app.domain import ops
from app.domain.models import Reservation
from app.lora_service.models import Outbox
from tests.assistant_util import ALL, NOW, campus, fix_clock, resv


def _pv(app, room_ids, date="2026-11-27"):
    d = {"intent": "event.add", "target": {},
         "set": {"rooms": room_ids, "dates": [date], "time": ["15:00", "18:00"], "type": 5,
                 "subject": "알고리즘 특강"},
         "pick": {}, "utterances": ["803 특강", "알고리즘 특강"]}
    return P.make_preview(app.state.Session, ALL, "c_t", d, NOW)


def _apply(app, pid, now=NOW, sc=ALL):
    return P.apply_preview(app.state.Session, sc, pid, now)


def test_apply_commits_what_preview_showed(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    code, body = _apply(app, pv["preview_id"])
    assert code == 200 and body["outbox_ids"]
    with app.state.Session() as s:
        assert P.week_data(s, ids["E803"], "2026-11-23") == pv["rooms"][0]["weeks"][0]["after"]
        ch = s.get(AssistantChange, body["change_id"])
        assert ch.utterance == "803 특강 / 알고리즘 특강" and json.loads(ch.summary) == pv["summary"]
        assert json.loads(ch.building_ids) == [ids["E"]] and json.loads(ch.outbox_ids) == body["outbox_ids"]
        assert ch.user_email == "admin@mju.ac.kr" and ch.school_id == 1
        assert s.get(AssistantPreview, pv["preview_id"]).applied_at is not None
        assert [o.type for o in s.scalars(select(Outbox))] == ["RESV_SET"]


def test_apply_twice_or_after_ttl_is_410(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    assert _apply(app, pv["preview_id"])[0] == 200
    assert _apply(app, pv["preview_id"]) == (410, {"detail": "expired"})
    pv2 = _pv(app, [ids["E801"]])
    assert _apply(app, pv2["preview_id"], NOW + dt.timedelta(minutes=11)) == (410, {"detail": "expired"})


def test_stale_preview_returns_new_preview(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    resv(app, ids["E803"], dt.date(2026, 11, 28), (9, 0), (10, 0), id_=50)  # 다른 관리자가 같은 방을 바꿈
    code, body = _apply(app, pv["preview_id"])
    assert code == 409 and body["detail"] == "stale"
    assert body["preview"]["preview_id"] != pv["preview_id"] and body["preview"]["blockers"] == []
    assert _apply(app, pv["preview_id"])[0] == 410  # 옛 미리보기는 더 못 쓴다
    assert _apply(app, body["preview"]["preview_id"])[0] == 200


def test_blocked_preview_is_422(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]], date="2026-11-24")  # 지난 날짜
    code, body = _apply(app, pv["preview_id"])
    assert code == 422 and body["detail"] == "blocked" and body["blockers"] == pv["blockers"]


def test_apply_is_atomic_across_rooms(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E801"], ids["E802"]])
    assert pv["blockers"] == []
    orig = ops.write_resv

    def boom(s, room_id, *a, **kw):
        if room_id == ids["E802"]:
            raise HTTPException(409, "용량 초과(테스트)")
        return orig(s, room_id, *a, **kw)

    monkeypatch.setattr(ops, "write_resv", boom)
    assert _apply(app, pv["preview_id"]) == (422, {"detail": "blocked", "blockers": ["용량 초과(테스트)"]})
    with app.state.Session() as s:
        assert s.scalar(select(func.count()).select_from(Reservation)) == 0  # 801 도 안 들어갔다
        assert s.scalar(select(func.count()).select_from(Outbox)) == 0
        assert s.get(AssistantPreview, pv["preview_id"]).applied_at is None


def test_other_admin_cannot_apply(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    pv = _pv(app, [ids["E803"]])
    other = Scope(1, None, "someone@mju.ac.kr")
    assert _apply(app, pv["preview_id"], sc=other) == (404, {"detail": "미리보기 없음"})
```

Run: `uv run pytest tests/test_assistant_apply.py -q`
Expected: FAIL — `AttributeError: module 'app.assistant.preview' has no attribute 'apply_preview'`.

- [ ] **Step 2: 모델 안내 파일**

`server/app/assistant/model.json` (릴리스 PR 만 바꾼다 — 02 작업지시서):
```json
{"enabled": false}
```

`server/app/assistant/manifest.py`:
```python
"""모델 안내 (공통 부록 §4.1). model.json 은 릴리스 PR 이 바꾸는 유일한 파일이다 —
runtime·repo·revision·files·generation 만 거기 있고, 지시문·출력 문법·접두어는 assistant_proto 에서 채운다."""

from __future__ import annotations

import json
import re
from pathlib import Path

from assistant_proto import FIRST_PREFIX, SCHEMA_VERSION, SYSTEM_PROMPT, json_schema

MODEL_FILE = Path(__file__).with_name("model.json")
RUNTIMES = ("webllm", "transformers", "litert", "wllama")
DEFAULT_GENERATION = {"temperature": 0, "max_tokens": 256}
_REV = re.compile(r"^[0-9a-f]{40}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _read(path: Path | None) -> dict:
    return json.loads((path or MODEL_FILE).read_text(encoding="utf-8"))


def _valid_file(f: object) -> bool:
    return (
        isinstance(f, dict)
        and isinstance(f.get("name"), str)
        and bool(f["name"])
        and isinstance(f.get("size"), int)
        and f["size"] > 0
        and isinstance(f.get("sha256"), str)
        and bool(_SHA.match(f["sha256"]))
    )


def load(path: Path | None = None) -> dict:
    d = _read(path)
    if not d.get("enabled"):
        return {"enabled": False}
    ok = (
        d.get("runtime") in RUNTIMES
        and isinstance(d.get("repo"), str)
        and d["repo"].count("/") == 1
        and isinstance(d.get("revision"), str)
        and bool(_REV.match(d["revision"]))  # 브랜치 이름이 아니라 커밋 해시로 고정
        and isinstance(d.get("files"), list)
        and bool(d["files"])
        and all(_valid_file(f) for f in d["files"])
    )
    if not ok:
        raise ValueError("model.json 형식이 틀렸습니다 — runtime·repo·revision(40자)·files[name,size,sha256]")
    return {
        "enabled": True,
        "schema_v": SCHEMA_VERSION,
        "runtime": d["runtime"],
        "repo": d["repo"],
        "revision": d["revision"],
        "files": d["files"],
        "system_prompt": SYSTEM_PROMPT,
        "first_prefix": FIRST_PREFIX,
        "json_schema": json_schema(),
        "generation": d.get("generation", DEFAULT_GENERATION),
    }


def current_revision(path: Path | None = None) -> str | None:
    """기록에 남길 모델 판. 안내가 없거나 읽을 수 없으면 None."""
    try:
        d = _read(path)
    except (OSError, ValueError):
        return None
    return d.get("revision") if d.get("enabled") else None
```

- [ ] **Step 3: `apply_preview`**

`server/app/assistant/preview.py` import 에 더한다:
```python
from app.assistant import changes, manifest
from app.assistant.models import AssistantChange, AssistantPreview
```
(기존 두 줄 `from app.assistant import changes`·`from app.assistant.models import AssistantPreview` 를 위로 바꾼다.)

파일 끝에 붙인다:
```python
def apply_preview(
    Session: sessionmaker, sc: Scope, preview_id: str, now_local: dt.datetime
) -> tuple[int, dict]:
    now_utc = clock.to_utc(now_local)
    stale: tuple[str, dict] | None = None
    with R._ID_LOCK, Session() as s:
        p = s.get(AssistantPreview, preview_id)
        if p is None or p.user_email != sc.email:
            return 404, {"detail": "미리보기 없음"}
        if p.applied_at is not None or p.expires_at <= now_utc:
            return 410, {"detail": "expired"}
        blockers = json.loads(p.blockers)
        if blockers:
            return 422, {"detail": "blocked", "blockers": blockers}
        room_ids = json.loads(p.room_ids)
        if fingerprint(s, room_ids) != p.fingerprint:
            stale = (p.conversation_id, json.loads(p.draft))
            p.expires_at = now_utc  # 옛 미리보기는 더 못 쓴다
            s.commit()
        else:
            try:
                ids, modems = run_ops(s, sc, json.loads(p.ops), sc.email, now_local)
            except _OP_ERRORS as e:
                s.rollback()  # 한 트랜잭션 — 하나라도 실패하면 아무것도 바뀌지 않는다
                return 422, {"detail": "blocked", "blockers": [_message(e)]}
            draft = json.loads(p.draft)
            bids = sorted(set(s.scalars(select(Room.building_id).where(Room.id.in_(room_ids)))))
            ch = AssistantChange(
                preview_id=p.id,
                user_email=sc.email,
                school_id=sc.school_id,
                building_ids=_j(bids),
                utterance=" / ".join(draft["utterances"]),
                ops=p.ops,
                summary=p.summary,
                outbox_ids=_j(ids),
                model_rev=manifest.current_revision(),
                applied_at=now_utc,
            )
            s.add(ch)
            p.applied_at = now_utc
            s.flush()
            change_id = ch.id
            s.commit()
    if stale is not None:  # 락 밖에서 — make_preview 가 락을 다시 잡는다(비재진입)
        return 409, {"detail": "stale", "preview": make_preview(Session, sc, stale[0], stale[1], now_local)}
    for m in modems:
        api.notify(m)
    return 200, {"change_id": change_id, "outbox_ids": ids}
```

- [ ] **Step 4: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_apply.py tests/test_assistant_preview.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

```bash
git add server/app/assistant/manifest.py server/app/assistant/model.json server/app/assistant/preview.py \
  server/tests/test_assistant_apply.py
git commit -m "feat(server): AI 비서 적용 — 지문 재검사(409+새 미리보기)·만료 410·막음 422·한 트랜잭션·변경 기록"
```

---

### Task 13: 조회 답 (`ask.*`)

**Files:**
- Create: `server/app/assistant/answers.py`
- Test: `server/tests/test_assistant_answers.py`

**Interfaces:**
- Consumes: `analytics.free_slots`, `admin.pending_reservations`, `admin.expected_nodes`, Task 10 의 `changes.md`·`span`·`TYPE`·`d_`·`hm`·`room_labels`
- Produces: `answers.answer(s, sc, draft, now_local) -> dict` — 부록 `AnswerOut` `{"title", "columns", "rows"}`

| intent | 쓰는 초안 칸 | 열 |
|---|---|---|
| `ask.free_rooms` | `dates[0]`, (선택) `time`·`rooms` | 강의실 · 빈 시간 |
| `ask.schedule` | `rooms`, (선택) `dates` — 없으면 이번 주, 최대 14일 | 강의실 · 날짜 · 시각 · 유형 · 이름 · 구분 |
| `ask.requests` | (선택) `rooms`·`dates` | 강의실 · 날짜 · 시각 · 신청자 · 이름 |
| `ask.node` | `rooms` | 강의실 · 유닛 · 배터리 · 신호 · 마지막 응답 · 상태 |

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_answers.py`:
```python
import datetime as dt

from app.assistant import answers as A
from tests.assistant_util import ALL, NOW, campus, resv


def _ans(app, intent, target):
    draft = {"intent": intent, "target": target, "set": {}, "pick": {}, "utterances": ["u"]}
    with app.state.Session() as s:
        return A.answer(s, ALL, draft, NOW)


def test_free_rooms_window(app, school):
    campus(app)
    a = _ans(app, "ask.free_rooms", {"dates": ["2026-11-27"], "time": ["15:00", "16:00"]})
    labels = [r[0] for r in a["rows"]]
    assert "공학관 803" not in labels  # 금 15:00–16:15 자료구조
    assert {"공학관 801", "인문관 803"} <= set(labels) and "타교관 803" not in labels
    assert a["columns"] == ["강의실", "빈 시간"]
    assert a["title"] == f"11/27(금) 15:00~16:00 빈 강의실 {len(a['rows'])}곳"


def test_free_rooms_limited_to_rooms(app, school):
    ids = campus(app)
    a = _ans(app, "ask.free_rooms", {"dates": ["2026-11-27"], "rooms": [ids["E803"]]})
    assert a["rows"] == [["공학관 803", "09:00–15:00, 16:15–21:00"]]


def test_schedule_defaults_to_this_week(app, school):
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 26), (13, 0), (14, 0), id_=9, subject="세미나")
    a = _ans(app, "ask.schedule", {"rooms": [ids["E803"]]})
    assert a["rows"] == [
        ["공학관 803", "11/23(월)", "09:00–12:00", "수업", "알고리즘", "정규"],
        ["공학관 803", "11/26(목)", "13:00–14:00", "특강", "세미나", "승인"],
        ["공학관 803", "11/27(금)", "15:00–16:15", "수업", "자료구조", "정규"],
    ]
    assert a["title"] == "11/23(월)~11/29(일) 일정 3건"


def test_requests_list(app, school, students):
    ids = campus(app)
    resv(app, ids["E801"], dt.date(2026, 11, 26), (13, 0), (14, 0), id_=31, type_=6,
         subject="스터디", status="requested", requested_by="s1@mju.ac.kr")
    a = _ans(app, "ask.requests", {})
    assert a["rows"] == [["공학관 801", "11/26(목)", "13:00–14:00", "학생1", "스터디"]]
    assert _ans(app, "ask.requests", {"rooms": [ids["E802"]]})["rows"] == []


def test_node_status(app, school):
    ids = campus(app)
    a = _ans(app, "ask.node", {"rooms": [ids["E803"]]})
    assert a["rows"] == [["공학관 803", "1", "-", "-", "-", "응답 없음"]]
    assert a["title"] == "노드 1대"
```

Run: `uv run pytest tests/test_assistant_answers.py -q`
Expected: FAIL — `ImportError: cannot import name 'answers'`.

- [ ] **Step 2: 구현**

`server/app/assistant/answers.py`:
```python
"""조회 답 (ask.*, spec §4) — 확인 화면 없이 표 하나. 기존 집계 함수를 그대로 쓴다."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.changes import TYPE, d_, hm, md, room_labels, span
from app.auth.scope import Scope
from app.domain import admin, analytics, clock, reserve
from app.domain.models import ExamPeriod, Reservation, Slot

SCHEDULE_DAYS_MAX = 14
_WARN = {"unseen": "응답 없음", "low_batt": "배터리 낮음", "resync": "재동기 필요", "clock_stale": "시계 오래됨"}


def _min(hhmm: str) -> int:
    h, m = hm(hhmm)
    return h * 60 + m


def answer(s: Session, sc: Scope, draft: dict, now_local: dt.datetime) -> dict:
    fn = {"ask.free_rooms": _free, "ask.schedule": _schedule, "ask.requests": _requests, "ask.node": _node}
    return fn[draft["intent"]](s, sc, draft["target"], now_local)


def _free(s, sc, tg, now_local) -> dict:
    d = d_(tg["dates"][0])
    window = None
    if "time" in tg:
        window = (_min(tg["time"][0]), _min(tg["time"][1]) if tg["time"][1] else reserve.CLOSE_MIN)
    rows = []
    for r in analytics.free_slots(s, sc, d, None):
        if "rooms" in tg and r["room_id"] not in tg["rooms"]:
            continue
        spans = [(x["from"], x["to"]) for x in r["free"]]
        if window:
            spans = [(a, b) for a, b in spans if _min(a) <= window[0] and window[1] <= _min(b)]
        if spans:
            rows.append([f"{r['building']} {r['room']}", ", ".join(f"{a}–{b}" for a, b in spans)])
    when = md(d) + (f" {tg['time'][0]}~{tg['time'][1] or ''}" if "time" in tg else "")
    return {"title": f"{when} 빈 강의실 {len(rows)}곳", "columns": ["강의실", "빈 시간"], "rows": rows}


def _schedule(s, sc, tg, now_local) -> dict:
    if "dates" in tg:
        days = [d_(x) for x in tg["dates"]][:SCHEDULE_DAYS_MAX]
    else:
        mon = clock.week_start(now_local.date())
        days = [mon + dt.timedelta(days=i) for i in range(7)]
    labels = room_labels(s, tg["rooms"])
    rows = []
    for rid in tg["rooms"]:
        for d in days:
            items = [
                (x.s_h, x.s_m, x.e_h, x.e_m, x.type, x.subject, "정규")
                for x in s.scalars(
                    select(Slot).where(Slot.room_id == rid, Slot.day == d.isoweekday(), Slot.type != 4)
                )
            ]
            items += [
                (r.s_h, r.s_m, r.e_h, r.e_m, r.type, r.subject, "승인" if r.status == "approved" else "신청")
                for r in s.scalars(
                    select(Reservation).where(
                        Reservation.room_id == rid,
                        Reservation.date == d,
                        Reservation.status.in_(("approved", "requested")),
                    )
                )
            ]
            for sh, sm, eh, em, t, subj, kind in sorted(items):
                rows.append([labels[rid], md(d), span(sh, sm, eh, em), TYPE[t], subj, kind])
        q = select(ExamPeriod).where(
            ExamPeriod.room_id == rid, ExamPeriod.date_start <= days[-1], ExamPeriod.date_end >= days[0]
        )
        for x in s.scalars(q):
            rows.append([labels[rid], f"{md(x.date_start)}~{md(x.date_end)}", "", "시험기간", "", ""])
    return {
        "title": f"{md(days[0])}~{md(days[-1])} 일정 {len(rows)}건",
        "columns": ["강의실", "날짜", "시각", "유형", "이름", "구분"],
        "rows": rows,
    }


def _requests(s, sc, tg, now_local) -> dict:
    rows = []
    for r in admin.pending_reservations(s, sc, now_local):
        if "rooms" in tg and r["room_id"] not in tg["rooms"]:
            continue
        if "dates" in tg and r["date"].isoformat() not in tg["dates"]:
            continue
        who = (r["requester"] or {}).get("name", "-")
        rows.append([f"{r['building']} {r['room']}", md(r["date"]), span(r["s_h"], r["s_m"], r["e_h"], r["e_m"]),
                     who, r["subject"]])
    return {"title": f"대기 중인 신청 {len(rows)}건", "columns": ["강의실", "날짜", "시각", "신청자", "이름"],
            "rows": rows}


def _node(s, sc, tg, now_local) -> dict:
    rows = []
    for n in admin.expected_nodes(s, sc):
        if n["room_id"] not in tg["rooms"]:
            continue
        batt = f"{n['batt_mv'] / 1000:.2f} V" if n["batt_mv"] else "-"
        rssi = f"{n['rssi']} dBm" if n["rssi"] is not None else "-"
        seen = clock.to_local(n["last_seen_at"]).strftime("%m/%d %H:%M") if n["last_seen_at"] else "-"
        state = ", ".join(_WARN[w] for w in n["warnings"]) or "정상"
        rows.append([f"{n['building']} {n['room']}", str(n["unit"]), batt, rssi, seen, state])
    return {"title": f"노드 {len(rows)}대", "columns": ["강의실", "유닛", "배터리", "신호", "마지막 응답", "상태"],
            "rows": rows}
```

- [ ] **Step 3: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_answers.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

```bash
git add server/app/assistant/answers.py server/tests/test_assistant_answers.py
git commit -m "feat(server): AI 비서 조회 답 — 빈 강의실·일정·대기 신청·노드 상태"
```

---

### Task 14: HTTP — 스키마 · 턴 처리 · 라우터 · 등록

**Files:**
- Create: `server/app/assistant/schemas.py`, `server/app/assistant/service.py`, `server/app/assistant/router.py`
- Modify: `server/app/main.py` (import 한 줄 + `include_router` 한 줄)
- Test: `server/tests/test_assistant_api.py`

**Interfaces:**
- Consumes: Task 9~13 전부, `ratelimit.check`
- Produces: 부록 §4 의 네 경로 그대로 — `GET /api/assistant/model`, `POST /api/assistant/turns`, `POST /api/assistant/previews/{preview_id}/apply`, `GET /api/assistant/changes?limit=50`
  - `service.handle_turn(Session, sc, body: TurnIn, now_local) -> dict`(TurnOut), `service.list_changes(Session, sc, limit) -> list[dict]`
  - `router.TURNS_PER_MIN = 60` (관리자 이메일당 분당 상한, 넘으면 429)
  - 대화 30분 만료(`service.CONV_TTL`), 매 턴 `assistant_turns` 기록, 미리보기 뒤에도 대화는 열려 있다(이어서 고치면 새 미리보기)

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_api.py`:
```python
import datetime as dt
import json

import pytest
from assistant_proto import SYSTEM_PROMPT
from sqlalchemy import select

from app.assistant import manifest
from app.assistant import router as assistant_router
from app.assistant.models import AssistantTurn
from tests.assistant_util import UTC_NOW, building_admin, campus, fix_clock, form, turn
from tests.conftest import _hdr

GOOD_MODEL = {
    "enabled": True,
    "runtime": "webllm",
    "repo": "4thIS/esc-assistant-e2b",
    "revision": "a" * 40,
    "files": [{"name": "model.bin", "size": 123, "sha256": "b" * 64}],
    "generation": {"temperature": 0, "max_tokens": 256},
}
FIRST = form("event.add", set_={"rooms": ["803호"], "when": "이번주 금요일",
                                "time": "15시부터 18시까지", "type": "특강"})
FIRST_TEXT = "803호 이번주 금요일 15시부터 18시까지 특강 예약해줘"


def test_model_disabled_by_default(client):
    assert client.get("/api/assistant/model").json() == {"enabled": False}
    assert manifest.load() == {"enabled": False} and manifest.current_revision() is None


def test_model_enabled_and_validated(client, tmp_path, monkeypatch):
    p = tmp_path / "model.json"
    p.write_text(json.dumps(GOOD_MODEL), encoding="utf-8")
    monkeypatch.setattr(manifest, "MODEL_FILE", p)
    j = client.get("/api/assistant/model").json()
    assert j["enabled"] and j["schema_v"] == 1 and j["revision"] == "a" * 40 and j["runtime"] == "webllm"
    assert j["system_prompt"] == SYSTEM_PROMPT and j["first_prefix"] == "관리자: "
    assert j["json_schema"]["properties"]["v"] == {"const": 1} and j["files"] == GOOD_MODEL["files"]
    assert manifest.current_revision() == "a" * 40
    p.write_text(json.dumps({**GOOD_MODEL, "revision": "main"}), encoding="utf-8")
    with pytest.raises(ValueError):
        manifest.load()


def test_flow_ask_fill_choose_preview_apply(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    j = turn(client, FIRST_TEXT, FIRST)
    assert j["kind"] == "ask" and j["message"] == "특강 이름은 무엇인가요?" and not j["closed"]
    assert j["next_prefix"] == (
        "상태: event.add | 강의실 803호 | 날짜 이번주 금요일 | 시각 15시부터 18시까지 | 유형 특강 | 이름 ?\n"
        "질문: 특강 이름은 무엇인가요?\n관리자: "
    )
    conv = j["conversation_id"]
    j = turn(client, "알고리즘 특강이요", form("fill", set_={"subject": "알고리즘 특강"}), conv=conv)
    assert j["kind"] == "ask" and [c["label"] for c in j["choices"]] == ["공학관 803", "인문관 803"]
    j = turn(client, "공학관 803", conv=conv, choice=f"room:{ids['E803']}")
    assert j["kind"] == "preview" and j["preview"]["blockers"] == [] and not j["closed"]
    assert j["next_prefix"].endswith(
        "질문: 확인 화면을 보고 [적용]을 눌러 주세요. 바꿀 것이 있으면 말씀해 주세요.\n관리자: "
    )
    assert j["preview"]["expires_at"].endswith("Z")
    pid = j["preview"]["preview_id"]
    r = client.post(f"/api/assistant/previews/{pid}/apply")
    assert r.status_code == 200 and r.json()["outbox_ids"]
    rows = client.get(f"/api/rooms/{ids['E803']}/reservations").json()
    assert [(x["subject"], x["date"], x["s_h"], x["e_h"]) for x in rows] == [("알고리즘 특강", "2026-11-27", 15, 18)]
    assert client.post(f"/api/assistant/previews/{pid}/apply").status_code == 410
    [ch] = client.get("/api/assistant/changes").json()
    assert ch["summary"] == j["preview"]["summary"] and ch["utterance"].startswith(FIRST_TEXT)
    assert ch["applied_at"].endswith("Z")


def test_refine_after_preview_makes_new_preview(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    f = form("event.add", set_={"rooms": ["공학관 803"], "when": "이번주 금요일", "time": "17시~18시",
                                "type": "특강", "subject": "세미나"})
    j = turn(client, "공학관 803 금 17~18 세미나 특강", f)
    assert j["kind"] == "preview"
    j2 = turn(client, "아 801도", form("fill", set_={"rooms": ["공학관 801"]}), conv=j["conversation_id"])
    assert j2["kind"] == "preview" and j2["preview"]["preview_id"] != j["preview"]["preview_id"]
    assert {r["room_id"] for r in j2["preview"]["rooms"]} == {ids["E803"], ids["E801"]}


def test_schema_version_and_body_shape(client):
    r = client.post("/api/assistant/turns",
                    json={"conversation_id": None, "utterance": "x", "form": {**form("cancel"), "v": 2}})
    assert r.status_code == 409 and r.json() == {"detail": "schema_version"}
    assert client.post("/api/assistant/turns", json={"utterance": "x"}).status_code == 422
    both = {"utterance": "x", "form": form("cancel"), "choice": "room:1"}
    assert client.post("/api/assistant/turns", json=both).status_code == 422
    also_raw = {"utterance": "x", "form": form("cancel"), "raw_output": "{"}
    assert client.post("/api/assistant/turns", json=also_raw).status_code == 422


def test_raw_output_is_logged_and_answered_as_error(client, app):
    r = client.post("/api/assistant/turns", json={"utterance": "803 금 특강", "raw_output": "{\"v\":1,\"intent\""})
    j = r.json()
    assert r.status_code == 200 and j["kind"] == "error" and j["closed"]
    assert j["message"].startswith("요청을 이해하지 못했습니다")
    with app.state.Session() as s:
        t = s.scalars(select(AssistantTurn).order_by(AssistantTurn.id.desc())).first()
        assert t.form == "{\"v\":1,\"intent\"" and t.reply_kind == "error"


def test_requires_manager(client_raw, student_hdr):
    assert client_raw.get("/api/assistant/model").status_code == 401
    assert client_raw.get("/api/assistant/model", headers=student_hdr).status_code == 403
    r = client_raw.post("/api/assistant/turns", json={"utterance": "x", "form": form("cancel")},
                        headers=student_hdr)
    assert r.status_code == 403


def test_rate_limited(client, monkeypatch):
    monkeypatch.setattr(assistant_router, "TURNS_PER_MIN", 2)
    for _ in range(2):
        turn(client, "취소", form("cancel"))
    r = client.post("/api/assistant/turns", json={"utterance": "취소", "form": form("cancel")})
    assert r.status_code == 429


def test_cancel_unknown_fill_and_bad_choice(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, "취소", form("cancel"))
    assert (j["kind"], j["message"], j["closed"], j["next_prefix"]) == ("answer", "취소했습니다.", True, None)
    j = turn(client, "안녕", form("unknown"))
    assert j["kind"] == "error" and j["closed"] and j["message"].startswith("그 요청은 AI 비서가 할 수 없습니다")
    j = turn(client, "자료구조", form("fill", set_={"subject": "자료구조"}))
    assert j["kind"] == "error" and j["message"].startswith("무엇을 할지 먼저 말씀해 주세요")
    j = turn(client, FIRST_TEXT, FIRST)
    j = turn(client, "아무거나", conv=j["conversation_id"], choice="room:999999")
    assert j["kind"] == "error" and not j["closed"] and j["message"].startswith("그 선택지는 지금 고를 수 없습니다")
    j = turn(client, "x", {"v": 1, "intent": "event.add", "target": {}, "set": {"rooms": []}},
             conv=j["conversation_id"])
    assert j["kind"] == "error" and j["message"].startswith("요청을 이해하지 못했습니다")


def test_answer_closes_conversation(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, "공학관 803 노드 상태", form("ask.node", target={"rooms": ["공학관 803"]}))
    assert j["kind"] == "answer" and j["closed"] and j["answer"]["columns"][0] == "강의실"


def test_expired_conversation(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, FIRST_TEXT, FIRST)
    fix_clock(monkeypatch, UTC_NOW + dt.timedelta(minutes=31))
    j = turn(client, "알고리즘 특강", form("fill", set_={"subject": "알고리즘 특강"}), conv=j["conversation_id"])
    assert (j["kind"], j["closed"]) == ("error", True)
    assert j["message"] == "대화가 만료되었습니다. 다시 말씀해 주세요."


def test_turns_are_logged(client, app, monkeypatch):
    fix_clock(monkeypatch)
    campus(app)
    j = turn(client, FIRST_TEXT, FIRST)
    turn(client, "알고리즘 특강이요", form("fill", set_={"subject": "알고리즘 특강"}), conv=j["conversation_id"])
    with app.state.Session() as s:
        rows = s.scalars(select(AssistantTurn).order_by(AssistantTurn.id)).all()
    assert [(r.utterance, r.reply_kind) for r in rows] == [(FIRST_TEXT, "ask"), ("알고리즘 특강이요", "ask")]
    assert json.loads(rows[0].form) == FIRST and rows[0].user_email == "admin@mju.ac.kr"
    assert rows[0].conversation_id == rows[1].conversation_id == j["conversation_id"]


def test_building_admin_scope(client, app, monkeypatch):
    fix_clock(monkeypatch)
    ids = campus(app)
    building_admin(app, "h@mju.ac.kr", [ids["H"]])
    h = _hdr(app, "h@mju.ac.kr")
    f = form("event.add", set_={"rooms": ["공학관 803"], "when": "이번주 금요일", "time": "17시~18시",
                                "type": "특강", "subject": "세미나"})
    j = turn(client, "공학관 803 세미나", f, headers=h)
    assert j["kind"] == "ask" and j["message"].startswith("'공학관 803' 강의실을 찾지 못했습니다")
    j = turn(client, "공학관 803 세미나", f)  # 최고 관리자
    pid = j["preview"]["preview_id"]
    assert client.post(f"/api/assistant/previews/{pid}/apply", headers=h).status_code == 404
    assert client.post(f"/api/assistant/previews/{pid}/apply").status_code == 200
    assert client.get("/api/assistant/changes", headers=h).json() == []
    assert len(client.get("/api/assistant/changes").json()) == 1
```

Run: `uv run pytest tests/test_assistant_api.py -q`
Expected: FAIL — `/api/assistant/*` 404 또는 `ImportError: cannot import name 'router'`.

- [ ] **Step 2: 스키마**

`server/app/assistant/schemas.py`:
```python
"""AI 비서 HTTP 모양 (공통 부록 §4). 주간 데이터는 기존 SlotWithRoom·ResvWithRoom·ExamWithRoom 그대로."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app import schemas as S


class TurnIn(BaseModel):
    conversation_id: str | None = Field(None, max_length=40)
    utterance: str = Field(min_length=1, max_length=300)
    form: dict | None = None
    choice: str | None = Field(None, max_length=80)
    # 브라우저가 두 번 시도해도 JSON 으로 못 읽은 모델 출력 원문 — 학습용 기록에 남기고 오류로 답한다
    raw_output: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _one(self):
        if sum(x is not None for x in (self.form, self.choice, self.raw_output)) != 1:
            raise ValueError("form · choice · raw_output 중 정확히 하나")
        return self


class Choice(BaseModel):
    id: str
    label: str


class Mark(BaseModel):
    entity: Literal["slot", "resv", "exam"]
    key: str
    op: Literal["add", "remove", "change"]
    fields: list[str] = []


class WeekData(BaseModel):
    slots: list[S.SlotWithRoom]
    reservations: list[S.ResvWithRoom]
    exams: list[S.ExamWithRoom]


class PreviewWeek(BaseModel):
    week_start: dt.date | None
    before: WeekData
    after: WeekData
    changes: list[Mark]


class PreviewRoom(BaseModel):
    room_id: int
    building_id: int
    label: str
    added: int
    removed: int
    changed: int
    weeks: list[PreviewWeek]


class PreviewOut(BaseModel):
    preview_id: str
    expires_at: dt.datetime
    summary: list[str]
    blockers: list[str]
    warnings: list[str]
    notices: list[str]
    rooms: list[PreviewRoom]


class AnswerOut(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[str]]


class TurnOut(BaseModel):
    conversation_id: str
    kind: Literal["ask", "preview", "answer", "error"]
    message: str
    choices: list[Choice] = []
    next_prefix: str | None = None
    closed: bool = False
    preview: PreviewOut | None = None
    answer: AnswerOut | None = None


class ChangeOut(BaseModel):
    id: int
    applied_at: dt.datetime
    user_email: str
    utterance: str
    summary: list[str]
    outbox_ids: list[int]
```

- [ ] **Step 3: 턴 처리**

`server/app/assistant/service.py`:
```python
"""턴 처리 — 대화 상태 읽기 → 반영 → 진행 → 저장·기록 (spec §4·§5.5). 라우터는 이 모듈만 부른다.
세션은 단계마다 새로 연다 — 미리보기(별도 세션에서 쓰고 되돌림)와 쓰기 잠금이 엇갈리지 않게."""

from __future__ import annotations

import datetime as dt
import json
import secrets

from assistant_proto import FormError, parse_form, render_prefix, rules
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.assistant import answers, dialog, manifest, preview
from app.assistant.models import AssistantChange, AssistantConversation, AssistantTurn
from app.assistant.schemas import TurnIn
from app.auth.scope import Scope
from app.domain import clock

CONV_TTL = dt.timedelta(minutes=30)
EXAMPLE = "예: '803호 이번 주 금요일 15시부터 18시까지 특강 등록해줘'"
CAN_DO = (
    "일정·시험기간·정규 시간표의 등록·수정·삭제, 학생 신청 승인·거절, "
    "빈 강의실·일정·신청·노드 조회를 할 수 있습니다."
)
EXPIRED = "대화가 만료되었습니다. 다시 말씀해 주세요."
PREVIEW_Q = "확인 화면을 보고 [적용]을 눌러 주세요. 바꿀 것이 있으면 말씀해 주세요."


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _prefix(state: dict, slot: str | None, question: str) -> str:
    items = rules.state_items(state["intent"], state["target"], state["set"], slot)
    return render_prefix(state["intent"], items, question)


def _out(conv_id, kind, message, *, choices=None, prefix=None, closed=False, pv=None, answer=None) -> dict:
    return {
        "conversation_id": conv_id,
        "kind": kind,
        "message": message,
        "choices": choices or [],
        "next_prefix": None if closed else prefix,
        "closed": closed,
        "preview": pv,
        "answer": answer,
    }


def _keep(conv_id: str, state: dict | None, message: str) -> dict:
    """오류 — 진행 중인 대화가 있으면 그대로 두고 이어서 말하게 한다."""
    if state is None:
        return _out(conv_id, "error", message, closed=True)
    return _out(conv_id, "error", message, prefix=_prefix(state, state.get("asked"), message))


def _step(Session, sc: Scope, conv_id: str, state: dict | None, body: TurnIn, now_local):
    lead = ""
    try:
        if body.raw_output is not None:
            raise FormError("모델 출력이 JSON 이 아님")
        if body.form is not None:
            state, lead = dialog.absorb(state, parse_form(body.form), body.utterance)
        else:
            state = dialog.choose(state, body.choice, body.utterance)
    except FormError:
        return _keep(conv_id, state, "요청을 이해하지 못했습니다. 다르게 말씀해 주세요. " + EXAMPLE), state
    except dialog.Unsupported:
        return _keep(conv_id, state, "그 요청은 AI 비서가 할 수 없습니다. " + CAN_DO), state
    except dialog.NeedContext:
        if body.choice is not None:
            return _keep(conv_id, state, "그 선택지는 지금 고를 수 없습니다. 다시 말씀해 주세요."), state
        return _keep(conv_id, state, "무엇을 할지 먼저 말씀해 주세요. " + EXAMPLE), state
    if state is None:  # 취소
        return _out(conv_id, "answer", lead, closed=True), None
    with Session() as s:
        d = dialog.advance(s, sc, state, now_local)
        if isinstance(d, dialog.Answer):
            ans = answers.answer(s, sc, d.draft, now_local)
            return _out(conv_id, "answer", lead + ans["title"], closed=True, answer=ans), None
    if isinstance(d, dialog.Ask):
        prefix = _prefix(d.state, d.state["asked"], d.question)
        return _out(conv_id, "ask", lead + d.question, choices=d.choices, prefix=prefix), d.state
    if isinstance(d, dialog.Fail):
        return _out(conv_id, "error", lead + d.message, prefix=_prefix(d.state, None, d.message)), d.state
    pv = preview.make_preview(Session, sc, conv_id, d.draft, now_local)
    msg = (
        "적용할 수 없는 변경이 있습니다. 오른쪽에서 이유를 확인해 주세요."
        if pv["blockers"]
        else "오른쪽에서 바뀌는 내용을 확인하고 [적용]을 눌러 주세요."
    )
    return _out(conv_id, "preview", lead + msg, prefix=_prefix(d.state, None, PREVIEW_Q), pv=pv), d.state


def _save(Session, sc: Scope, conv_id: str, state: dict | None, now_utc: dt.datetime) -> None:
    with Session() as s, s.begin():
        c = s.get(AssistantConversation, conv_id)
        if c is None:
            if state is not None:
                s.add(AssistantConversation(id=conv_id, user_email=sc.email, state=_j(state),
                                            created_at=now_utc, updated_at=now_utc))
            return
        c.state, c.updated_at = _j(state), now_utc
        if state is None:
            c.closed_at = now_utc


def _log(Session, sc: Scope, conv_id: str, body: TurnIn, out: dict, now_utc: dt.datetime) -> None:
    with Session() as s, s.begin():
        s.add(AssistantTurn(
            conversation_id=conv_id,
            user_email=sc.email,
            utterance=body.utterance,
            form=_j(body.form) if body.form is not None else body.raw_output,
            choice=body.choice,
            reply_kind=out["kind"],
            reply_message=out["message"],
            model_rev=manifest.current_revision(),
            created_at=now_utc,
        ))


def handle_turn(Session: sessionmaker, sc: Scope, body: TurnIn, now_local: dt.datetime) -> dict:
    now_utc = clock.to_utc(now_local)
    conv_id, state = body.conversation_id, None
    if conv_id is not None:
        with Session() as s:
            c = s.get(AssistantConversation, conv_id)
            alive = (
                c is not None
                and c.user_email == sc.email
                and c.closed_at is None
                and now_utc - c.updated_at <= CONV_TTL
            )
            state = json.loads(c.state) if alive else None
        if not alive:
            out = _out(conv_id, "error", EXPIRED, closed=True)
            _log(Session, sc, conv_id, body, out, now_utc)
            return out
    else:
        conv_id = "c_" + secrets.token_hex(8)
    out, new_state = _step(Session, sc, conv_id, state, body, now_local)
    _save(Session, sc, conv_id, new_state, now_utc)
    _log(Session, sc, conv_id, body, out, now_utc)
    return out


def list_changes(Session: sessionmaker, sc: Scope, limit: int) -> list[dict]:
    """자기 범위의 변경 기록 — 건물 관리자는 맡은 건물 안에서만 바뀐 것."""
    out = []
    with Session() as s:
        q = (
            select(AssistantChange)
            .where(AssistantChange.school_id == sc.school_id)
            .order_by(AssistantChange.id.desc())
            .limit(500)
        )
        for c in s.scalars(q):
            if sc.buildings is not None and not set(json.loads(c.building_ids)) <= sc.buildings:
                continue
            out.append({
                "id": c.id,
                "applied_at": c.applied_at.replace(tzinfo=dt.UTC),
                "user_email": c.user_email,
                "utterance": c.utterance,
                "summary": json.loads(c.summary),
                "outbox_ids": json.loads(c.outbox_ids),
            })
            if len(out) >= limit:
                break
    return out
```

- [ ] **Step 4: 라우터 + 등록**

`server/app/assistant/router.py`:
```python
"""/api/assistant/* (공통 부록 §4). 관리자 + 건물 범위(MgrScope). 핸들러는 요청 세션(_DB)에 쓰지 않고
request.app.state.Session 으로 직접 연다 — 미리보기가 다른 세션에서 쓰고 되돌리므로 SQLite 쓰기 잠금이 엇갈리지 않게."""

from __future__ import annotations

from assistant_proto import SCHEMA_VERSION
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.assistant import manifest, preview, service
from app.assistant import schemas as AS
from app.auth import ratelimit
from app.auth.deps import ManagerUser, MgrScope
from app.auth.scope import Scope
from app.domain import clock

router = APIRouter(prefix="/api/assistant", dependencies=[ManagerUser])
TURNS_PER_MIN = 60  # 관리자 이메일당 — 테스트가 바꿔 끼운다


@router.get("/model")
def model_info() -> dict:
    return manifest.load()


@router.post("/turns", response_model=AS.TurnOut)
def turns(body: AS.TurnIn, request: Request, sc: Scope = MgrScope):
    if body.form is not None and body.form.get("v") != SCHEMA_VERSION:
        return JSONResponse({"detail": "schema_version"}, status_code=409)
    if not ratelimit.check(f"assistant:{sc.email}", limit=TURNS_PER_MIN):
        raise HTTPException(429, "잠시 후 다시 시도하세요")
    return service.handle_turn(request.app.state.Session, sc, body, clock.local_now())


@router.post("/previews/{preview_id}/apply")
def apply(preview_id: str, request: Request, sc: Scope = MgrScope):
    code, body = preview.apply_preview(request.app.state.Session, sc, preview_id, clock.local_now())
    return JSONResponse(jsonable_encoder(body), status_code=code)


@router.get("/changes", response_model=list[AS.ChangeOut])
def changes(request: Request, limit: int = Query(50, ge=1, le=200), sc: Scope = MgrScope):
    return service.list_changes(request.app.state.Session, sc, limit)
```

`server/app/main.py`:
- import 묶음(`from app.auth import password` 근처, 알파벳 순)에:
```python
from app.assistant.router import router as assistant_router
```
- `app.include_router(student_router)` 아래에:
```python
    app.include_router(assistant_router)
```

- [ ] **Step 5: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_api.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

```bash
git add server/app/assistant/schemas.py server/app/assistant/service.py server/app/assistant/router.py \
  server/app/main.py server/tests/test_assistant_api.py
git commit -m "feat(server): AI 비서 HTTP — /api/assistant 모델 안내·턴·적용·변경 기록, 30분 대화·분당 상한·턴 기록"
```

---

### Task 15: 오래된 기록 정리 (매일 작업, wj 리뷰)

**Files:**
- Create: `server/app/assistant/prune.py`
- Modify: `server/app/domain/daily.py` (import 한 줄 · `res` 초기값 한 칸 · `step` 한 줄)
- Test: `server/tests/test_assistant_prune.py`

**Interfaces:**
- Produces: `prune.prune(s, now_utc) -> {"turns": n, "conversations": n, "previews": n}` — 턴 기록 180일, 대화(마지막 말 기준) 1일, 미리보기(만료 기준) 1일 지난 것을 지운다. 매일 작업 결과 JSON 에 `"assistant"` 키로 남는다(기존 `"pruned"` 는 그대로).

- [ ] **Step 1: 실패하는 테스트**

`server/tests/test_assistant_prune.py`:
```python
import datetime as dt
import json

from app.assistant import prune
from app.assistant.models import AssistantConversation, AssistantPreview, AssistantTurn
from app.domain import daily
from app.domain.models import JobRun
from tests.assistant_util import UTC_NOW, fix_clock


def _seed(app):
    old, new = UTC_NOW - dt.timedelta(days=181), UTC_NOW - dt.timedelta(days=1, hours=-1)
    with app.state.Session() as s, s.begin():
        for i, t in enumerate((old, new)):
            s.add(AssistantTurn(conversation_id=f"c{i}", user_email="admin@mju.ac.kr", utterance="u",
                                reply_kind="ask", reply_message="m", created_at=t))
        for i, t in enumerate((UTC_NOW - dt.timedelta(days=2), UTC_NOW)):
            s.add(AssistantConversation(id=f"c_{i}", user_email="admin@mju.ac.kr", state="null",
                                        created_at=t, updated_at=t))
            s.add(AssistantPreview(id=f"p_{i}", conversation_id=f"c_{i}", user_email="admin@mju.ac.kr",
                                   draft="{}", ops="[]", room_ids="[]", fingerprint="x", blockers="[]",
                                   summary="[]", created_at=t, expires_at=t))


def test_prune_removes_only_old_rows(app, school):
    _seed(app)
    with app.state.Session() as s, s.begin():
        assert prune.prune(s, UTC_NOW) == {"turns": 1, "conversations": 1, "previews": 1}
    with app.state.Session() as s, s.begin():
        assert prune.prune(s, UTC_NOW) == {"turns": 0, "conversations": 0, "previews": 0}


def test_daily_runs_assistant_step(app, school, monkeypatch):
    fix_clock(monkeypatch)
    _seed(app)
    with app.state.Session() as s:
        res = json.loads(s.get(JobRun, daily.run_daily(app.state.Session)).result)
    assert res["errors"] == [] and res["assistant"] == {"turns": 1, "conversations": 1, "previews": 1}
    assert set(res["pruned"]) == {"reservations", "job_runs", "email_tokens", "rejected_signups"}
```

Run: `uv run pytest tests/test_assistant_prune.py -q`
Expected: FAIL — `ImportError: cannot import name 'prune'`.

- [ ] **Step 2: 구현**

`server/app/assistant/prune.py`:
```python
"""오래된 AI 비서 기록 정리 — 매일 작업(app.domain.daily)이 부른다 (spec §5.5: 턴 기록 180일)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.assistant.models import AssistantConversation, AssistantPreview, AssistantTurn

TURN_KEEP_DAYS = 180
CONV_KEEP_DAYS = 1  # 30분이면 만료 — 하루 지나면 지운다
PREVIEW_KEEP_DAYS = 1  # 10분이면 만료 — 변경 기록은 preview_id 문자열만 가진다


def prune(s: Session, now_utc: dt.datetime) -> dict:
    turn_cut = now_utc - dt.timedelta(days=TURN_KEEP_DAYS)
    conv_cut = now_utc - dt.timedelta(days=CONV_KEEP_DAYS)
    pv_cut = now_utc - dt.timedelta(days=PREVIEW_KEEP_DAYS)
    return {
        "turns": s.execute(delete(AssistantTurn).where(AssistantTurn.created_at < turn_cut)).rowcount,
        "conversations": s.execute(
            delete(AssistantConversation).where(AssistantConversation.updated_at < conv_cut)
        ).rowcount,
        "previews": s.execute(
            delete(AssistantPreview).where(AssistantPreview.expires_at < pv_cut)
        ).rowcount,
    }
```

`server/app/domain/daily.py`:
- import 에 한 줄:
```python
from app.assistant import prune as assistant_prune
```
- `_run_daily` 의 `res` 초기값을:
```python
    res: dict = {
        "expired": 0, "promoted": 0, "resynced": [], "pruned": {}, "assistant": {}, "errors": []
    }
```
- `step("pruned", ...)` 바로 아래에:
```python
    step("assistant", lambda s: assistant_prune.prune(s, now_utc))
```

- [ ] **Step 3: 통과 + 커밋**

Run: `uv run pytest tests/test_assistant_prune.py tests/test_daily.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS — `tests/test_daily.py` 는 고치지 않는다(`"pruned"` 모양 불변).

```bash
git add server/app/assistant/prune.py server/app/domain/daily.py server/tests/test_assistant_prune.py
git commit -m "feat(server): 매일 작업에 AI 비서 기록 정리 — 턴 180일·대화·미리보기 1일"
```

---

### Task 16: 보장 테스트 — "미리보기 = 적용" 전 작업

**Files:**
- Test: `server/tests/test_assistant_guarantees.py`

**Interfaces:**
- Consumes: `preview.make_preview`·`apply_preview`·`week_data` (Task 11·12)

- [ ] **Step 1: 테스트 작성**

`server/tests/test_assistant_guarantees.py`:
```python
"""spec §13 — 모든 바꾸는 작업에서 (1) 미리보기는 아무것도 남기지 않고 (2) 적용 결과가 미리보기의 '바뀐 뒤'와 같다."""

import datetime as dt

import pytest
from sqlalchemy import func, select

from app.assistant import preview as P
from app.domain.models import ExamPeriod, Reservation, Slot
from app.lora_service.models import Outbox
from tests.assistant_util import ALL, NOW, campus, fix_clock, resv


def _d(intent, target=None, set_=None):
    return {"intent": intent, "target": target or {}, "set": set_ or {}, "pick": {}, "utterances": ["u"]}


CASES = {
    "event.add": lambda i: _d("event.add", set_={"rooms": [i["E801"], i["E802"]], "dates": ["2026-11-27"],
                                                 "time": ["10:00", "12:00"], "type": 6, "subject": "대관"}),
    "event.add.holiday": lambda i: _d("event.add", set_={
        "rooms": [i["E803"]], "dates": ["2026-11-30"], "type": 3,
        "entries": [{"room_id": i["E803"], "date": "2026-11-30", "start": "09:00", "end": "12:00",
                     "subject": "알고리즘", "professor": "이"}]}),
    "event.change": lambda i: _d("event.change", target={"rooms": [i["E803"]], "dates": ["2026-11-27"], "type": 5},
                                 set_={"time": ["19:00", None]}),
    "event.remove": lambda i: _d("event.remove", target={"rooms": [i["E803"]], "dates": ["2026-11-27"], "type": 5}),
    "exam.add": lambda i: _d("exam.add", set_={"rooms": [i["E801"]], "range": ["2026-12-14", "2026-12-18"]}),
    "exam.change": lambda i: _d("exam.change", target={"rooms": [i["E803"]]},
                                set_={"range": ["2026-12-15", "2026-12-19"]}),
    "exam.remove": lambda i: _d("exam.remove", target={"rooms": [i["E803"]]}),
    "class.add": lambda i: _d("class.add", set_={"rooms": [i["E801"]], "weekdays": [2, 4], "time": ["09:00", "10:30"],
                                                 "type": 1, "subject": "운영체제"}),
    "class.change": lambda i: _d("class.change", target={"rooms": [i["E803"]], "weekdays": [1], "subject": "알고리즘"},
                                 set_={"weekdays": [3], "time": ["13:00", None]}),
    "class.remove": lambda i: _d("class.remove", target={"rooms": [i["E803"]], "weekdays": [5], "subject": "자료구조"}),
    "request.approve": lambda i: _d("request.approve", target={"requester": "학생1"}),
    "request.reject": lambda i: _d("request.reject", target={"requester": "학생1"}, set_={"reason": "점검"}),
}


def _counts(app):
    with app.state.Session() as s:
        return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Slot, Reservation, ExamPeriod, Outbox))


@pytest.mark.parametrize("case", list(CASES))
def test_preview_leaves_nothing_and_equals_apply(client, app, students, monkeypatch, case):
    fix_clock(monkeypatch)
    ids = campus(app)
    resv(app, ids["E803"], dt.date(2026, 11, 27), (17, 0), (18, 0), id_=17)
    resv(app, ids["E801"], dt.date(2026, 11, 26), (13, 0), (14, 0), id_=31, type_=6, subject="스터디",
         status="requested", requested_by="s1@mju.ac.kr")
    with app.state.Session() as s, s.begin():
        s.add(ExamPeriod(id=5, room_id=ids["E803"], date_start=dt.date(2026, 12, 14),
                         date_end=dt.date(2026, 12, 18)))
    before = _counts(app)
    pv = P.make_preview(app.state.Session, ALL, "c_t", CASES[case](ids), NOW)
    assert pv["blockers"] == [], pv["blockers"]
    assert _counts(app) == before  # (1) 미리보기는 흔적이 없다
    assert any(w["changes"] for r in pv["rooms"] for w in r["weeks"]), case
    code, body = P.apply_preview(app.state.Session, ALL, pv["preview_id"], NOW)
    assert code == 200, body
    with app.state.Session() as s:  # (2) 적용 = 미리보기의 '바뀐 뒤'
        for room in pv["rooms"]:
            for w in room["weeks"]:
                got = P.week_data(s, room["room_id"], w["week_start"])
                assert got == w["after"], (case, room["label"], w["week_start"])
```

- [ ] **Step 2: 실행 — 실패하면 구현을 고친다**

Run: `uv run pytest tests/test_assistant_guarantees.py -q`
Expected: PASS 12개. 하나라도 실패하면 **테스트가 아니라** `changes.py`(op 만들기)·`preview.py`(run_ops·week_data)를 고친다 — 이 테스트가 spec §5 의 핵심 보장이다.

- [ ] **Step 3: 커밋**

```bash
git add server/tests/test_assistant_guarantees.py
git commit -m "test(server): AI 비서 보장 — 12가지 작업에서 미리보기 무흔적·미리보기 = 적용"
```

---

### Task 17: PR B 게이트 + PR

- [ ] **Step 1: 전체 게이트**

```bash
cd assistant_proto && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && cd ..
cd server && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && cd ..
git diff --stat main -- server/tests/ | grep -v "assistant\|test_domain_ops" || true   # 기존 테스트 파일 변경 0 이어야 한다
```
Expected: 전부 PASS, 마지막 줄은 요약 한 줄(`N files changed`)만 — 기존 테스트 파일 이름이 나오면 안 된다.

선택: Docker 가 있으면 리포 루트에서 `docker compose build && docker compose up -d` 후
`curl -s localhost:8000/api/health` → `{"ok":true}`, 그리고 `docker compose down` (**`-v` 금지** — 운영 DB 를 지운다).

- [ ] **Step 2: PR**

```bash
git push -u origin feature/assistant-server
gh pr create --base main --title "feat(server): 관리자 AI 비서 백엔드 — 대화·미리보기·적용 (/api/assistant)" --body-file - <<'EOF'
## 요약
spec `docs/specs/2026-11-25-admin-ai-assistant-design.md` §4~§6·§9~§13, 공통 부록 §4 그대로.

- `app/domain/ops.py`: 커밋하지 않는 쓰기로 정리 — 기존 라우터 동작·테스트 불변 (**wj 리뷰**)
- 새 표 4개(`web_assistant` 마이그레이션): 대화·턴 기록(180일)·미리보기(10분)·변경 기록
- 강의실 해석(건물 범위) · 대화(되묻기·선택지·휴강 펼치기·대상 찾기) · 확정 변경 목록
- 미리보기: 같은 쓰기 함수로 실행 → 전·후 주간표 → rollback (흔적 0)
- 적용: 지문 재검사(409 + 새 미리보기) · 410 · 422 · 한 트랜잭션 · 변경 기록
- 조회 답 4종 · `GET /api/assistant/model`(`model.json` = `{"enabled": false}` — 모델 릴리스 PR 이 켠다)
- 매일 작업에 기록 정리 한 단계 (`daily.py` 한 줄, **wj 리뷰**)
- Docker 이미지에 `assistant_proto/` · CI 필터·스모크

## 선행
- PR A(`feat(proto): assistant_proto v1`) 머지 뒤. 이 PR 은 그 규격을 쓴다.
- 새 필수 env 없음. 마이그레이션은 컨테이너 시작 때 `alembic upgrade head`.

## 게이트
- assistant_proto: (통과 수)
- server: (통과 수) — 기존 테스트 파일 변경 없음
- 보장 테스트 12가지: 미리보기 무흔적 · 미리보기 = 적용
EOF
```

---

## PR C — 문서: 역할 표 · AI 비서 영역 · 홈서버 배포 (독립)

### Task 18: `CLAUDE.md` · `server/CLAUDE.md` · CODEOWNERS

**Files:**
- Modify: `CLAUDE.md`, `server/CLAUDE.md`, `.github/CODEOWNERS`

**Interfaces:** 없음 (문서)

```bash
git switch main && git pull --ff-only && git switch -c docs/assistant-roles
```

- [ ] **Step 1: 루트 `CLAUDE.md`**

1. "프로젝트 개요" 의 `- 배포:` 줄 전체를 바꾼다:
```markdown
- 배포: **2026-11-24 부터 메인Pi 역할(웹서버·DB)은 홈서버 myserver 가 맡는다** — `/srv/apps/Woo-ESC-Capston` 에서 Docker Compose(루트 `compose.yaml` + `server/Dockerfile`, 포트는 git 밖 `compose.override.yaml`), 공개 주소는 Cloudflare 터널 `esc.ssenu.cloud`. 홈서버의 사용자 타이머 `esc-autodeploy.timer` 가 2분마다 `main` 을 받아 server·web 이 바뀐 경우만 다시 빌드한다 — 그래서 `main` 머지가 곧 운영 반영이다. 옛 메인Pi(Raspberry Pi)는 정지·되돌리기용으로 보관한다(`deploy/autodeploy/` 는 그 시절 것). 노트북에서도 같은 명령(`docker compose up -d --build`)으로 띄운다. **모뎀Pi 는 systemd**(USB 시리얼·시계 동기에 직접 붙어야 해서). CI 는 검증만 한다.
```
2. "역할 분담" 표의 cw·wj 줄을 바꾸고 mh 줄을 지운다:
```markdown
| cw | @ssenu (Owner) | 전 영역 총괄 + `lora_proto/` + `firmware/` 무선·스케줄링 + `modempi/lora/` + `assistant_proto/`·`server/app/assistant/`(AI 비서) + `docs/design/` | 설계(spec/plan)·계약·인프라·최종 승인. LoRa 파이프라인(전처리→송신). AI 비서 규격·백엔드. 웹 디자인 스펙 |
| wj | @leemonta9482 | `server/`(AI 비서 `server/app/assistant/` 제외), `web/` **전체**, `modempi/link/`, `ml/` | 서버·관리자/학생 웹 풀스택(디자인 스펙을 Vue 코드로 구현), 메인Pi↔모뎀Pi WebSocket 링크, AI 비서 모델 파인튜닝 |
```
표 바로 아래에 한 줄:
```markdown
mh(@jmh7706jmh-ops)는 2026-11-25 팀에서 빠졌다 — 웹 디자인 스펙(`docs/design/`)은 cw 가 쓰고 wj 가 구현한다.
```
3. "계층 규율" 표 — `lora_proto/` 줄 아래에 새 줄:
```markdown
| `assistant_proto/` | 관리자 AI 비서 양식 규격의 **단일 진실원** — 모델(`ml/`)·서버(`server/app/assistant/`)·웹이 같은 양식·지시문·해석 규칙·대화 규칙을 쓴다 | PM(@ssenu) 전담. 이 폴더만 바꾸는 PR 을 **단독으로 먼저** 머지(lockstep). 양식 판(`v`)을 올리면 모델 재학습이 따른다 |
```
그리고 `docs/design/` 줄의 셋째 칸을:
```markdown
| `docs/design/` ↔ `web/src/styles/`, `web/src/components/ui/` | 디자인 스펙(문서, cw) ↔ 디자인 토큰·디자인시스템(코드, wj) | **스펙이 원본, 코드는 구현.** 토큰 값·컴포넌트 variant를 바꾸려면 cw가 `docs/design/` PR을 먼저 머지하고 wj가 코드 PR로 따라간다(lockstep). 화면(`views/`)에서 토큰을 우회한 하드코딩 색·간격 금지 |
```
4. "폴더 구조 요약" 블록에 두 줄 추가(`lora_proto/` 아래, `web/` 아래):
```text
├── assistant_proto/ ← AI 비서 양식 규격: JSON Schema·해석기·대화 규칙·프롬프트·예문 (Owner 전담, lockstep)
├── ml/           ← AI 비서 모델 데이터·파인튜닝·평가·변환 (wj)
```
그리고 `docs/` 줄의 `design/ 은 mh의 디자인 스펙` → `design/ 은 디자인 스펙(cw)`.
5. "커밋 규칙" 블록에 두 줄 추가:
```text
feat(assistant): ...    # 관리자 AI 비서 서버·웹 (server/app/assistant, web/src/admin/assistant)
feat(ml): ...           # AI 비서 모델 학습·평가 (ml/)
```
6. "문서 인덱스" 표에 줄 추가, `docs/design/README.md` 줄의 `(mh → wj 계약)` → `(cw → wj 계약)`:
```markdown
| `docs/specs/2026-11-25-admin-ai-assistant-design.md` | 관리자 AI 비서 — 양식 채우기형, Gemma 4 E2B 파인튜닝·브라우저 실행, 전·후 비교 확인 후 적용 |
```

- [ ] **Step 2: `server/CLAUDE.md`**

1. "배포" 절의 첫 두 줄을 바꾼다:
```markdown
- 운영 서버(2026-11-24 부터 홈서버 myserver — 옛 메인Pi 대신)는 **루트 `compose.yaml` + `server/Dockerfile`** 로만 배포한다. 수동 `uvicorn` 실행·systemd 유닛은 개발용이다.
- **`main` 머지 = 운영 반영.** 홈서버의 사용자 타이머 `esc-autodeploy.timer`(`~/.local/bin/esc-autodeploy.sh`)가 2분 안에 받아 server·web 이 바뀐 경우만 다시 빌드한다(alembic 이 바뀌면 `main.db.predeploy` 를 먼저 떠 둔다). 새 필수 env 를 더하는 PR 은 머지 **전에** 홈서버 `/srv/apps/Woo-ESC-Capston/server/.env` 를 먼저 채운다.
```
2. 같은 절의 `운영 메인Pi 는 \`DEBUG=0\`` → `운영은 \`DEBUG=0\``.
3. "계층 책임" 절 끝에 새 줄:
```markdown
- `app/assistant/`(관리자 AI 비서)는 **cw 담당**이다. 양식·해석 규칙은 `../assistant_proto/` 가 원본이고, 도메인 쓰기는 `app/domain/ops.py` 의 커밋하지 않는 함수로만 한다(미리보기 rollback·적용 commit 이 같은 함수를 쓴다). 라우터에 새 쓰기 경로를 만들면 그 쓰기도 `ops.py` 에 둔다.
```

- [ ] **Step 3: CODEOWNERS**

`.github/CODEOWNERS`:
- `/lora_proto/                        @ssenu` 아래에:
```text
/assistant_proto/                   @ssenu
```
- server 절 `/server/app/lora_service/           @ssenu` 아래에:
```text
/server/app/assistant/              @ssenu
/server/app/domain/ops.py           @ssenu @leemonta9482
```
- web 절 아래에 새 절:
```text
# ─── ml: AI 비서 모델 데이터·학습·평가 (wj) ─────────────
/ml/                                @leemonta9482
```
- `/docs/design/                       @jmh7706jmh-ops` → `/docs/design/                       @ssenu`

- [ ] **Step 4: 커밋 + PR**

Run: `git diff --stat` — 세 파일만.

```bash
git add CLAUDE.md server/CLAUDE.md .github/CODEOWNERS
git commit -m "docs: 역할 표 — mh 제외·AI 비서 영역(assistant_proto·server/app/assistant=cw, ml=wj)·홈서버 배포 서술"
git push -u origin docs/assistant-roles
gh pr create --base main --title "docs: 역할 표 — mh 제외 · AI 비서 영역 · 홈서버 배포" --body-file - <<'EOF'
- mh 팀 제외(2026-11-25): `docs/design/` 스펙은 cw 가 쓰고 wj 가 구현
- AI 비서 영역: `assistant_proto/`·`server/app/assistant/` = cw, `ml/` = wj (CODEOWNERS 포함)
- 배포 서술: 메인Pi → 홈서버 myserver(`/srv/apps`, `esc-autodeploy.timer`, `esc.ssenu.cloud`)
문서만 바뀐다 — 코드·CI 영향 없음.
EOF
```

---

## 이후

- **머지 순서**: PR A(규격, 단독) → PR B(서버). PR C(문서)는 아무 때나. 웹 작업지시서 03 의 Task 0(화면 스펙, cw)도 PR B 와 독립.
- **배포**: PR B 머지 = 홈서버 반영(`esc-autodeploy`). 컨테이너 시작 때 `web_assistant` 마이그레이션이 돈다. `model.json` 이 `{"enabled": false}` 라 웹 AI 비서 탭은 "준비 중" — 백엔드를 모델보다 먼저 배포해도 안전하다.
- **모델 켜기**: 02 작업지시서(wj)의 릴리스 PR 이 `server/app/assistant/model.json` 을 `{"enabled": true, "runtime", "repo", "revision"(40자), "files", "generation"}` 으로 바꾼다. cw 가 합격선 보고서를 확인하고 머지.
- **웹**: 03 작업지시서가 이 API(부록 §4)만 쓴다. 개발 중에는 `form` 에 양식 JSON 을 직접 넣는 대역으로 이 서버를 그대로 쓸 수 있다.
- **2단계**: 되돌리기(`POST /api/assistant/changes/{id}/revert` — `assistant_changes.ops` 로 반대 변경 계산), 학습용 기록 내보내기(이름 지우기) — 별도 작업지시서.
