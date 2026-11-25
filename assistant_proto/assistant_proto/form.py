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
TYPE_LABELS: tuple[str, ...] = (
    "수업",
    "시험",
    "휴강",
    "빈강의실",
    "특강",
    "대여",
)  # = 서버 type 1~6
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
